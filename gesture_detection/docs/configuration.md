# 設定ファイル

[READMEに戻る](../README.md)

`gesture_detection/config.example.toml` を `config.toml` にコピーして編集します。
設定ファイルは省略できます。設定されていないキーには既定値が使われます。
ファイルを分けたい場合は `GESTURE_CONFIG_PATH=profiles/live.toml` のように指定します。
設定ファイル内の相対パスも、設定ファイル自体の相対パスもプロジェクトルートが基準です。
`GESTURE_PROJECT_ROOT` を使うインストール環境ではそのディレクトリが基準になります。
キーの誤記や型の違いは起動時にエラーとなります。

```toml
[camera]
indices = [] # 空配列なら実行時に映像から選択。2台の場合は役割の順番で指定

[multicam]
enabled = true

[multicam.first]
select_subject = true

[multicam.second]
select_subject = false

[output]
record_live = true
```

## `.env` からの移行

従来の `.env` は読み込みません。既存の値を `config.toml` の対応するテーブルへ移してください。
TOMLでは真偽値は `true` / `false`、配列は `[0, 2]` のように記述します。
空のパスは `""`、カメラの自動選択は `indices = []` です。

| 旧環境変数 | 新しいTOML項目 |
| ---------- | -------------- |
| `CAMERA_INDICES` | `camera.indices` |
| `CAMERA_SCAN_MAX_INDEX` | `camera.scan_max_index` |
| `CAMERA_BACKEND` | `camera.backend` |
| `CAMERA_FOURCC` | `camera.fourcc` |
| `FPS` | `camera.fps` |
| `VIDEO_SOURCE` | `video.source` |
| `OUTPUT_DIR` | `output.directory` |
| `VIDEO_OUTPUT_PATH` | `output.path` |
| `RECORD_LIVE_VIDEO` | `output.record_live` |
| `VIDEO_OUTPUT_BUFFER_FRAMES` | `output.buffer_frames` |
| `POSE_MODEL_PATH` | `models.pose` |
| `YOLO_MODEL_PATH` | `models.yolo` |
| `POSE_RUNNING_MODE` | `pose.running_mode` |
| `POSE_DISPLAY_SMOOTHING` | `pose.display_smoothing` |
| `POSE_SELECT_SUBJECT` | `pose.select_subject` |
| `SUBJECT_AREA` | `pose.subject.area` |
| `SUBJECT_MIN_TORSO_HEIGHT` | `pose.subject.min_torso_height` |
| `SUBJECT_MIN_SHOULDER_WIDTH` | `pose.subject.min_shoulder_width` |
| `RAMUNE_DETECTOR` | `ramune.detector` |
| `RAMUNE_LEARNED_MODEL_PATH` | `ramune.learned_model` |
| `MULTICAM_ENABLED` | `multicam.enabled` |
| `MULTICAM_HEADLESS` | `multicam.headless` |
| `MULTICAM_WIDTH` | `multicam.width` |
| `MULTICAM_HEIGHT` | `multicam.height` |
| `MULTICAM_FIRST_SELECT_SUBJECT` | `multicam.first.select_subject` |
| `MULTICAM_SECOND_SELECT_SUBJECT` | `multicam.second.select_subject` |
| `MULTICAM_VIDEO_SESSION` | `multicam.replay.session` |
| `MULTICAM_TRACE_PATH` | `diagnostics.multicam_trace` |
| `GESTURE_EVENT_TTL` | `events.ttl_seconds` |
| `SUPPRESS_MEDIAPIPE_STARTUP_LOGS` | `diagnostics.suppress_mediapipe_startup_logs` |

`GESTURE_PROJECT_ROOT` は実行環境のプロジェクトルートを指定する環境変数として残ります。
以前の `CAMERA_INDEX` / `MULTICAM_CAMERA_INDICES` を使っていた場合も
`camera.indices` に移してください。認識を伴わない `record-cameras` コマンドの引数は従来どおりです。
