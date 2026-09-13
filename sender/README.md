# macOS 图片发送工具

使用 Python 3.10+、Bleak/CoreBluetooth 和 Pillow。图片会按屏幕比例自动选择方向，等比缩放到 768×552 内，居中留白，经过 Atkinson 黑白黄红四色转换后通过蓝牙发送。无须配置 Wi-Fi。

先应用图片自身的 EXIF 方向，再比较原方向与顺时针旋转 90° 后等比缩放的屏幕占用面积。只有旋转后占用面积更大时才顺时针旋转一次；面积相同或变小则不旋转。例如 552×768 的竖图会转成 768×552，正方形图片保持原方向。预览与实际发送使用同一处理结果，不裁剪、不拉伸。

## 首次安装

在本目录打开终端：

```bash
python3 --version
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

使用装有 Python 3.10 或更高版本的 `python3`。首次扫描时允许终端访问蓝牙；若权限曾被拒绝，可在 macOS「系统设置 → 隐私与安全性 → 蓝牙」中允许运行工具的终端程序，再重启终端。

macOS 使用设备 UUID 标识 BLE 外设，扫描结果中的标识不是 MAC 地址；工具直接连接，无需在系统蓝牙界面预先配对。这些行为来自 [Bleak 的 macOS 后端说明](https://bleak.readthedocs.io/en/latest/backends/macos.html)。

## 扫描和发送

```bash
source .venv/bin/activate
python send_image.py --scan
python send_image.py test-card.png --preview preview.png
python send_image.py /path/to/photo.jpg
```

附近只有一台 InkBLE 设备时自动连接。多台设备时指定名称或扫描得到的 UUID：

```bash
python send_image.py photo.jpg --device InkBLE-A1-ABCD
```

工具显示上传进度，上传完成后等待电子纸刷新。看到“屏幕刷新完成”才表示设备报告刷新成功，随后连接自动释放。再次运行发送命令即可更新下一张图。

启动固件时屏幕会保留旧图，这是正常行为。`test-card.png` 包含 A/B/C/D 四角、可读方向文字、四色块、渐变和贯穿中间的网格，适合先验证屏幕。

## 只看转换结果

```bash
python send_image.py photo.jpg --prepare-only --preview preview.png
open preview.png
```

该命令不使用蓝牙。支持 Pillow 可读取的 PNG、JPEG、WebP 等格式；请先把 HEIC 导出为 JPEG/PNG。JPEG 的 EXIF 方向会自动应用，透明区域合成到白底。

```bash
# 同时导出设备所需的 105984 字节 2bpp 数据
python send_image.py photo.jpg --prepare-only --preview preview.png --raw-output image.2bpp
```

## 连接问题

- 扫描不到：确认设备已刷入 InkBLE 固件并通电、Mac 蓝牙已开启、终端已获蓝牙权限、设备未被另一客户端占用。
- 大数据包写入失败：工具会尝试读取已接收偏移并改用最小包；也可直接加 `--packet-size 20`，传输速度会降低。
- 接收过程中断线：保留原画面，重新运行发送命令，从头上传。
- 已提交之后断线或等待超时：设备仍会继续刷新。先查看屏幕，再决定是否重新发送；发送器不会将未确认完成的刷新报为成功。
- `屏幕 BUSY 超时`：检查刷入的 A0/A1 版本是否对应硬件，并保留串口日志供排查。

`--refresh-timeout 180` 控制等待刷新秒数，`--scan-seconds 6` 控制扫描时长。运行 `python send_image.py --help` 查看全部参数。

依赖固定在 `requirements.txt`。开发测试使用了真实 C++ 接收状态机和模拟 GATT；macOS 实际蓝牙连接仍需在 Mac 与设备上验证。
