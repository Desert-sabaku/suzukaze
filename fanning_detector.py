import multiprocessing as mp
import os
import queue
import time
import urllib.request
from collections import deque

import cv2
import mediapipe as mp_core
import numpy as np
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
from ultralytics import YOLO

# 定数・設定
MODEL_PATH = "pose_landmarker_lite.task"
MODEL_URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
FPS = 30
WINDOW_SEC = 2
BUFFER_SIZE = FPS * WINDOW_SEC
TARGET_LMS = [0, 11, 12, 15, 16]

# なぜか自分で定義する必要があるらしい
POSE_CONNECTIONS = [
    (0, 1),
    (1, 2),
    (2, 3),
    (3, 7),
    (0, 4),
    (4, 5),
    (5, 6),
    (6, 8),
    (9, 10),
    (11, 12),
    (11, 13),
    (13, 15),
    (15, 17),
    (15, 19),
    (15, 21),
    (17, 19),
    (12, 14),
    (14, 16),
    (16, 18),
    (16, 20),
    (16, 22),
    (18, 20),
    (11, 23),
    (12, 24),
    (23, 24),
    (23, 25),
    (24, 26),
    (25, 27),
    (26, 28),
    (27, 29),
    (28, 30),
    (29, 31),
    (30, 32),
    (27, 31),
    (28, 32),
]


# Workerプロセス (推論・演算プレーン)
def mediapipe_worker(frame_queue, result_queue):
    """別プロセスで動作し、MediaPipe推論と時系列判定に専念するワーカー"""

    # 1. モデルの準備 (プロセス内で独立して初期化する必要がある)
    if not os.path.exists(MODEL_PATH):
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)

    base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
    options = vision.PoseLandmarkerOptions(
        base_options=base_options,
        output_segmentation_masks=False,
        min_pose_detection_confidence=0.5,
        min_pose_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    landmarker = vision.PoseLandmarker.create_from_options(options)

    # 状態管理バッファ
    # このプロセス内だけで状態を持つ
    wrist_y_history = deque(maxlen=BUFFER_SIZE)
    motion_history = deque(maxlen=FPS * 1)
    prev_landmarks = None

    while True:
        # メインプロセスから画像が来るまで待機
        frame = frame_queue.get()
        if frame is None:
            break

        # 推論用に入力画像を変換
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp_core.Image(image_format=mp_core.ImageFormat.SRGB, data=rgb_frame)

        # 推論実行
        detection_result = landmarker.detect(mp_image)

        # 返却用データの構築
        result_data = {"landmarks": [], "messages": []}

        if len(detection_result.pose_landmarks) > 0:
            pose_landmarks = detection_result.pose_landmarks[0]

            # 描画用の座標を抽出
            result_data["landmarks"] = [
                (lm.x, lm.y, lm.visibility) for lm in pose_landmarks
            ]

            # 夕涼み(静止)の判定ロジック
            current_lms = np.array(
                [[pose_landmarks[i].x, pose_landmarks[i].y] for i in TARGET_LMS]
            )
            if prev_landmarks is not None:
                diff = np.linalg.norm(current_lms - prev_landmarks, axis=1)
                mean_motion = np.mean(diff)
                motion_history.append(mean_motion)
            prev_landmarks = current_lms

            # 扇ぐ判定ロジック
            wrist_lm = pose_landmarks[16]
            if wrist_lm.visibility > 0.5:
                wrist_y_history.append(wrist_lm.y)

                if len(wrist_y_history) == BUFFER_SIZE:
                    signal = np.array(wrist_y_history)
                    signal = signal - np.mean(signal)
                    fft_vals = np.abs(np.fft.fft(signal))
                    freqs = np.fft.fftfreq(BUFFER_SIZE, d=1 / FPS)

                    pos_mask = freqs > 0
                    freqs = freqs[pos_mask]
                    fft_vals = fft_vals[pos_mask]

                    target_mask = (freqs >= 1.0) & (freqs <= 3.0)
                    if np.any(target_mask):
                        max_amplitude = np.max(fft_vals[target_mask])
                        result_data["messages"].append(
                            (
                                f"Fanning Amp: {max_amplitude:.2f}",
                                (10, 30),
                                (0, 255, 0),
                                0.7,
                            )
                        )
                        if max_amplitude > 1.5:
                            result_data["messages"].append(
                                ("Action: Fanning!", (10, 80), (0, 165, 255), 1.2)
                            )

            # 夕涼み判定のメッセージ追加
            if len(motion_history) == motion_history.maxlen:
                avg_motion = np.mean(motion_history)
                result_data["messages"].append(
                    (f"Motion: {avg_motion:.4f}", (10, 55), (255, 200, 0), 0.7)
                )
                if avg_motion < 0.002:
                    result_data["messages"].append(
                        ("Action: Relaxing...", (10, 130), (255, 150, 150), 1.2)
                    )

        # 結果の送信 (古い結果があれば破棄して最新版に上書き)
        while not result_queue.empty():
            try:
                result_queue.get_nowait()
            except queue.Empty:
                pass
        result_queue.put(result_data)

    landmarker.close()


# YOLO Workerプロセス (物体検出プレーン)
def yolo_worker(frame_queue, result_queue):
    """別プロセスで動作し、YOLOによる物体検出に専念するワーカー"""
    # YOLOv8 nanoモデルの読み込み (初回は自動的にダウンロードされます)
    model = YOLO("yolov8n.pt")

    while True:
        frame = frame_queue.get()
        if frame is None:
            break

        # 推論実行
        results = model(frame, verbose=False)

        result_data = {
            "boxes": []
            # messageの送信は廃止し、メインプロセス側の状態で生成する
        }

        # YOLOの結果はlist[Results]またはNoneを返す場合があるため、
        # 事前に安全に反復・存在確認してからアクセスする
        for result in results or []:
            if result is None:
                continue

            boxes = getattr(result, "boxes", None)
            if boxes is None:
                continue

            for box in boxes:
                cls_id = int(box.cls[0])
                conf = float(box.conf[0])
                # 確信度50%以上のボトルを検出
                if cls_id == 39 and conf > 0.5:
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    result_data["boxes"].append(
                        (int(x1), int(y1), int(x2), int(y2), conf)
                    )

        # 結果の送信
        while not result_queue.empty():
            try:
                result_queue.get_nowait()
            except queue.Empty:
                pass
        result_queue.put(result_data)


# Mainプロセス (コントロール・UIプレーン)
def draw_landmarks_from_data(image, landmarks_data, connections):
    """メタデータ(座標リスト)から描画を行う"""
    h, w, _ = image.shape
    for connection in connections:
        start_idx, end_idx = connection
        if start_idx < len(landmarks_data) and end_idx < len(landmarks_data):
            sx, sy, s_vis = landmarks_data[start_idx]
            ex, ey, e_vis = landmarks_data[end_idx]
            if s_vis > 0.5 and e_vis > 0.5:
                cv2.line(
                    image,
                    (int(sx * w), int(sy * h)),
                    (int(ex * w), int(ey * h)),
                    (255, 255, 255),
                    2,
                )

    for x, y, vis in landmarks_data:
        if vis > 0.5:
            cv2.circle(image, (int(x * w), int(y * h)), 3, (0, 0, 255), -1)


def main():
    # MediaPipe用プロセス間通信キュー
    mp_frame_queue = mp.Queue(maxsize=1)
    mp_result_queue = mp.Queue(maxsize=1)

    # YOLO用プロセス間通信キュー
    yolo_frame_queue = mp.Queue(maxsize=1)
    yolo_result_queue = mp.Queue(maxsize=1)

    # ワーカープロセスの起動
    mp_worker = mp.Process(
        target=mediapipe_worker, args=(mp_frame_queue, mp_result_queue)
    )
    mp_worker.start()

    yolo_worker_process = mp.Process(
        target=yolo_worker, args=(yolo_frame_queue, yolo_result_queue)
    )
    yolo_worker_process.start()

    cap = cv2.VideoCapture(0)

    prev_time = time.time()
    latest_mp_result = {"landmarks": [], "messages": []}

    # 平滑化・保持用
    yolo_state = {
        "box": None,
        "conf": 0.0,
        "last_seen": 0,
    }
    YOLO_TTL = 0.5
    YOLO_EMA_ALPHA = 0.3  # 1に近いほど最新値を重視、0に近いほど滑らか

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        #  各ワーカーへ最新フレームを送信
        if mp_frame_queue.full():
            try:
                mp_frame_queue.get_nowait()
            except queue.Empty:
                pass
        mp_frame_queue.put(frame.copy())

        if yolo_frame_queue.full():
            try:
                yolo_frame_queue.get_nowait()
            except queue.Empty:
                pass
        yolo_frame_queue.put(frame.copy())

        # ワーカーから最新の推論結果を受信
        try:
            latest_mp_result = mp_result_queue.get_nowait()
        except queue.Empty:
            pass

        try:
            latest_yolo_result = yolo_result_queue.get_nowait()

            if latest_yolo_result["boxes"]:
                # 最も確信度が高いものを採用
                best_box = max(latest_yolo_result["boxes"], key=lambda b: b[4])
                current_box = np.array(best_box[:4])
                conf = best_box[4]

                # 初回、または見失ってからTTLが経過している場合は直接上書き
                if (
                    yolo_state["box"] is None
                    or (time.time() - yolo_state["last_seen"]) > YOLO_TTL
                ):
                    yolo_state["box"] = current_box
                else:
                    # 既に追従中の場合指数移動平均をかけて滑らかに更新
                    yolo_state["box"] = (
                        YOLO_EMA_ALPHA * current_box
                        + (1 - YOLO_EMA_ALPHA) * yolo_state["box"]
                    )

                yolo_state["conf"] = conf
                yolo_state["last_seen"] = time.time()
        except queue.Empty:
            pass

        # 描画処理
        annotated_image = frame.copy()

        draw_landmarks_from_data(
            annotated_image, latest_mp_result["landmarks"], POSE_CONNECTIONS
        )
        for text, pos, color, scale in latest_mp_result["messages"]:
            cv2.putText(
                annotated_image,
                text,
                pos,
                cv2.FONT_HERSHEY_SIMPLEX,
                scale,
                color,
                int(scale * 2),
            )

        # YOLO描画
        if (
            yolo_state["box"] is not None
            and (time.time() - yolo_state["last_seen"]) < YOLO_TTL
        ):
            x1, y1, x2, y2 = map(int, yolo_state["box"])
            cv2.rectangle(annotated_image, (x1, y1), (x2, y2), (0, 165, 255), 2)
            cv2.putText(
                annotated_image,
                f"Ramune Bottle: {yolo_state['conf']:.2f}",
                (x1, y1 - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 165, 255),
                2,
            )

        # カメラFPSの計算と表示
        curr_time = time.time()
        fps = 1 / (curr_time - prev_time)
        prev_time = curr_time
        cv2.putText(
            annotated_image,
            f"Main FPS: {fps:.1f}",
            (450, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (200, 200, 200),
            2,
        )

        cv2.imshow("Gesture Recognition (Async Pipeline)", annotated_image)

        if cv2.waitKey(1) & 0xFF == 27:
            break

    # クリーンアップ
    mp_frame_queue.put(None)
    yolo_frame_queue.put(None)
    mp_worker.join()
    yolo_worker_process.join()
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    # Windows等の環境でマルチプロセスを正常起動するために必要らしい
    mp.freeze_support()
    main()
