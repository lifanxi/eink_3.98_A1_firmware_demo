# 来源与许可

本项目从 [InkSight_adapt_HUAWEI_eink](https://github.com/krstc/InkSight_adapt_HUAWEI_eink) 中开发的独立 InkBLE 最简固件整理而来，保留原项目的 [MIT 许可证](LICENSE) 和版权声明。原 InkSight 项目版权归 datascale-ai。

屏幕初始化、A0/A1 行地址映射和左右方向修正参考了原项目中已适配的华为驱动；四色量化采用原项目使用的黑、白、黄、红近似色值和 Atkinson 误差扩散算法。蓝牙接收状态机与 macOS 图片发送流程属于独立最简固件的实现。

`tests/fixtures/` 中保存从原项目驱动捕获的合成测试图 SPI 输出，不是用户照片或原始参考固件。生成时使用的源码哈希、基准提交和输入说明记录在 `tests/fixtures/provenance.json` 中。该提交之外还包含当时本地的 A0/A1 适配修改，因此源码哈希是精确的追溯依据。

NimBLE-Arduino、Arduino ESP32、PlatformIO、Bleak 和 Pillow 由构建/安装工具获取，各自遵循上游许可证；本仓库不包含其源码、虚拟环境或访问凭据。
