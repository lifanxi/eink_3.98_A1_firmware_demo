# A1 预编译固件

`inkble_huawei_a1_full_0x0.bin` 是本仓库默认 A1 环境构建的完整合并镜像，包含引导程序、分区表和应用，刷写地址为 **0x0**。

- 芯片：ESP32-C3，Flash：DIO / 80 MHz / 4 MB。
- 镜像大小：564080 字节。
- SHA256：`a9511c08627e35f83c3663593de04f6c0f5dca3511e28025f3b85b46da3254bb`。
- 默认 A1 独立构建及 28 项主机测试通过；实际蓝牙连接和屏幕显示仍需实机验证。
- 工具验证了应用/引导程序校验和及 SHA256、分区表 MD5、factory 应用偏移 0x10000 和 NVS/PHY 空白区域。

构建来源和源码哈希记录在 [build-info.json](build-info.json)。A0 硬件请从仓库根目录执行 `pio run -e huawei_a0` 单独构建。

macOS 验证镜像（在本目录执行）：

```bash
shasum -a 256 -c SHA256SUMS
```

重新生成镜像与发送工具压缩包：

```bash
# 在仓库根目录、已激活开发环境时执行
pio run
python tools/package_release.py
```

新产物位于 `dist/ble-a1/`，打包脚本不会自动替换仓库中已有的预编译镜像。
