# mcu

`firmware/`(TinyGoファンコン)とUSBシリアルで通信するPythonクライアント。

```python
from mcu import FanController

with FanController("/dev/ttyACM0") as fan:
    fan.fade(pin=25, value=4000, duration_seconds=1.0)
```

pyserialがポートをraw modeで開くため、`stty raw -echo`は不要です。

## CLI

```bash
uv run mcu --port /dev/ttyACM0 --pin 25 --value 4000 --duration 1.0
```
