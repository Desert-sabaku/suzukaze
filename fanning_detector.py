import cv2
import numpy as np
import urllib.request
import os
from collections import deque
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

# ==========================================
# 1. AIモデル(.task)の準備 (Tasks APIの特徴)
# ==========================================
MODEL_PATH = 'pose_landmarker_lite.task'
MODEL_URL = 'https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task'

if not os.path.exists(MODEL_PATH):
    print(f"Downloading model to {MODEL_PATH}...")
    urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
    print("Download complete.")

# ==========================================
# 2. MediaPipe Tasks APIの初期化
# ==========================================
base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
options = vision.PoseLandmarkerOptions(
    base_options=base_options,
    output_segmentation_masks=False,
    min_pose_detection_confidence=0.5,
    min_pose_presence_confidence=0.5,
    min_tracking_confidence=0.5
)
landmarker = vision.PoseLandmarker.create_from_options(options)

# ==========================================
# 3. 描画用ユーティリティ（OpenCVによる自作）
# ==========================================
# 旧APIの POSE_CONNECTIONS 相当のインデックスペア
POSE_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 7), (0, 4), (4, 5), (5, 6), (6, 8), (9, 10),
    (11, 12), (11, 13), (13, 15), (15, 17), (15, 19), (15, 21), (17, 19),
    (12, 14), (14, 16), (16, 18), (16, 20), (16, 22), (18, 20), (11, 23),
    (12, 24), (23, 24), (23, 25), (24, 26), (25, 27), (26, 28), (27, 29),
    (28, 30), (29, 31), (30, 32), (27, 31), (28, 32)
]

def draw_landmarks(image, landmarks, connections):
    """OpenCVを使用してランドマークと接続線を描画する関数"""
    h, w, _ = image.shape
    
    # 接続線の描画
    for connection in connections:
        start_idx, end_idx = connection
        if start_idx < len(landmarks) and end_idx < len(landmarks):
            start_lm = landmarks[start_idx]
            end_lm = landmarks[end_idx]
            # visibilityのチェック (低スコアの部位は描画しない)
            if start_lm.visibility > 0.5 and end_lm.visibility > 0.5:
                start_point = (int(start_lm.x * w), int(start_lm.y * h))
                end_point = (int(end_lm.x * w), int(end_lm.y * h))
                cv2.line(image, start_point, end_point, (255, 255, 255), 2)
                
    # ランドマーク(点)の描画
    for landmark in landmarks:
        if landmark.visibility > 0.5:
            point = (int(landmark.x * w), int(landmark.y * h))
            cv2.circle(image, point, 3, (0, 0, 255), -1)

# ==========================================
# 4. 信号処理バッファの設定
# ==========================================
FPS = 30
WINDOW_SEC = 2
BUFFER_SIZE = FPS * WINDOW_SEC
wrist_y_history = deque(maxlen=BUFFER_SIZE)

# ==========================================
# 5. メインループ
# ==========================================
cap = cv2.VideoCapture(0)

while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        break

    # Tasks API用に入力画像を変換
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

    # 推論の実行
    detection_result = landmarker.detect(mp_image)
    
    # 描画用にBGRに戻す
    annotated_image = cv2.cvtColor(rgb_frame, cv2.COLOR_RGB2BGR)

    if len(detection_result.pose_landmarks) > 0:
        # 結果は複数人対応のリスト形式で返るため、0番目（1人目）を取得
        pose_landmarks = detection_result.pose_landmarks[0]
        
        # 自作関数による描画処理
        draw_landmarks(annotated_image, pose_landmarks, POSE_CONNECTIONS)

        # 16番が右手首 (Right Wrist)
        wrist_lm = pose_landmarks[16]
        
        # 認識の確信度が低い場合はバッファを更新しない(ノイズ対策)
        if wrist_lm.visibility > 0.5:
            wrist_y = wrist_lm.y
            wrist_y_history.append(wrist_y)

            # バッファが満杯になったらFFT解析を実行
            if len(wrist_y_history) == BUFFER_SIZE:
                signal = np.array(wrist_y_history)
                signal = signal - np.mean(signal) # 直流成分の除去

                # FFTの計算
                fft_vals = np.abs(np.fft.fft(signal))
                freqs = np.fft.fftfreq(BUFFER_SIZE, d=1/FPS)

                # 正の周波数帯のみ抽出
                pos_mask = freqs > 0
                freqs = freqs[pos_mask]
                fft_vals = fft_vals[pos_mask]

                # 1.0Hz 〜 3.0Hz の成分を取得
                target_mask = (freqs >= 1.0) & (freqs <= 3.0)
                
                if np.any(target_mask):
                    max_amplitude = np.max(fft_vals[target_mask])
                    
                    cv2.putText(annotated_image, f"Amplitude: {max_amplitude:.2f}", (10, 30), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                    
                    # 閾値判定
                    if max_amplitude > 1.5:
                        cv2.putText(annotated_image, "Action: Fanning!", (10, 80), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 165, 255), 3)

    cv2.imshow('Gesture Recognition (Tasks API)', annotated_image)
    
    # ESCキーで終了
    if cv2.waitKey(5) & 0xFF == 27:
        break

landmarker.close()
cap.release()
cv2.destroyAllWindows()
