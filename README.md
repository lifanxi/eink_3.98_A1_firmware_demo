# eink_3.98_A1_firmware_demo

华为 A0/A1 四色电子纸的最简 ESP32-C3 蓝牙图片固件，以及 macOS Python 图片发送工具。上电启动 BLE 服务，接收一张完整图片后刷新屏幕，继续等待下一次更新。**硬件版本在编译期选择，默认只构建 A1。**

## 功能

- 屏幕逻辑尺寸 **768×552**，支持黑、白、黄、红四色；上电保留屏幕已有画面。
- Mac 先应用 EXIF 方向，再比较原方向和顺时针旋转 90° 后的屏幕占用面积；只有旋转后更大才旋转一次，相同则保持原方向。
- 图片等比缩放、居中留白，不裁剪、不拉伸，使用 Atkinson 算法转换为四色。
- BLE 分包传送固定 105984 字节的 2bpp 图像，完整接收并通过 CRC32 校验、收到 COMMIT 后才刷新。
- 未提交的传输断线或 30 秒无有效数据会作废；已提交的图像即使断线仍继续刷新。
- 刷新后电子纸休眠，ESP32 保持蓝牙服务。一次允许一个连接，同一连接或再次连接均可更新下一张图。
- 图片缓存在 RAM，不写 Flash；无 Wi-Fi、配网、后端或自动轮播。

## 直接刷写 A1

仓库内提供 [A1 完整固件](prebuilt/inkble_huawei_a1_full_0x0.bin) 和 [SHA256 校验值](prebuilt/SHA256SUMS)，**刷写起始地址为 `0x0`**。构建与验证信息见 [预编译固件说明](prebuilt/README.md)。

使用 esptool 4.x 的示例：

```bash
python -m esptool --chip esp32c3 --port /dev/cu.usbmodemXXXX --baud 460800 \
  write_flash 0x0 prebuilt/inkble_huawei_a1_full_0x0.bin
```

本项目使用单 factory 应用分区，与旧 InkSight 的分区布局不同。首次迁移请刷完整合并镜像，或使用本项目的 PlatformIO upload；不要仅刷单独的应用 `firmware.bin`。`0xe000` 为 PHY 分区，不包含旧 OTA `boot_app0.bin`。

## macOS 发送图片

需要 Python 3.10+。从仓库根目录执行：

```bash
cd sender
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python send_image.py --scan
python send_image.py test-card.png --preview preview.png
python send_image.py /path/to/photo.jpg
```

首次扫描时允许终端访问蓝牙。附近只有一台 InkBLE 设备时自动连接；有多台时加 `--device InkBLE-A1-XXXX` 或扫描得到的 UUID。工具等待设备报告“屏幕刷新完成”后断开连接，再次运行发送命令即可更新下一张图。

只转换并查看预览：

```bash
python send_image.py /path/to/photo.jpg --prepare-only --preview preview.png
open preview.png
```

更多参数、权限与连接排查见 [发送工具说明](sender/README.md)。`test-card.png` 包含四角方向文字、四色块、渐变和中间网格，适合先检查显示。

## 从源码构建

需要 Python 3.10+。在仓库根目录创建开发环境：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
pio run
```

默认只构建 A1，合并镜像输出到 `.pio/build/huawei_a1/firmware_merged.bin`，刷写地址仍为 `0x0`。

```bash
# 刷写 A1 并查看串口日志
pio run -t upload --upload-port /dev/cu.usbmodemXXXX
pio device monitor --port /dev/cu.usbmodemXXXX

# 按需构建 A0
pio run -e huawei_a0
```

A0 产物在 `.pio/build/huawei_a0/`。`HUAWEI_EPD_REVISION` 默认为 1，A0 环境传入 0；不支持运行时切换，A1.1 尚未适配。

| 项目 | 配置 |
| --- | --- |
| 主控 | ESP32-C3 |
| Flash | 4 MB，DIO，80 MHz |
| 屏幕引脚 | MOSI=6、SCK=4、CS=7、DC=1、RST=2、BUSY=10（低电平忙） |
| 串口 | 原生 USB CDC，115200 |
| 蓝牙名称 | `InkBLE-A1-XXXX` / `InkBLE-A0-XXXX` |
| 图像缓存 | 105984 字节，静态分配 |
| 控制器地址 | 768×600，逐行映射逻辑 768×552 图像 |

构建依赖固定为 PlatformIO 6.2.0、Espressif32 6.12.0、Arduino ESP32 2.0.17 和 NimBLE-Arduino 2.5.1。

## 测试与打包

激活根目录开发环境后运行；主机测试还需要 `g++`（macOS 可使用 Xcode Command Line Tools 提供的 C++ 编译器）：

```bash
python tests/test_suite.py
python tools/package_release.py
```

28 项自动测试覆盖图片方向与白边、四色编码、BLE 分包、重复包、丢失应答、CRC 失败、断线、连续更新、接收超时、非法偏移，以及 A0/A1 屏幕 SPI 命令和 BUSY 超时。

屏幕测试编译本仓库的真实驱动，与 [原项目驱动捕获的固定参考数据](tests/fixtures/README.md) 逐字节比较。不依赖旧项目的目录或源码。打包脚本校验镜像、分区与校验和，输出 A1 完整镜像和 macOS 发送工具压缩包到 `dist/ble-a1/`。

主机测试不连接实物。原项目的 A1 屏幕方向已由实机反馈确认；新蓝牙固件与 macOS CoreBluetooth 的端到端通信仍需实机验证。

## 文件与协议

- `src/`：独立固件、屏幕驱动、BLE 接收状态机。
- `sender/`：Python 工具、Atkinson 转换和测试图。
- `tests/`：主机测试及独立屏幕参考数据。
- `tools/`：固件合并、打包和测试图生成脚本。
- `prebuilt/`：默认 A1 的完整可刷写镜像。

BLE UUID、消息格式、图像布局及连接生命周期见 [协议说明](PROTOCOL.md)。项目使用 [MIT 许可证](LICENSE)，来源与参考数据说明见 [NOTICE.md](NOTICE.md)。
