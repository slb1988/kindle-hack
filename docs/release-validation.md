# v0.2.1-ai-kit 验证记录

2026-11-01，本地合并 PR #2（休眠与退出门狗），并切换到 KPM / Scriptlet 安装路径。尚未完成本轮新包的全部真实 Kindle 功能实测。

| 检查 | 结果 |
| --- | --- |
| 安装器与设备流程 | 21 项通过：KPM 包复制、哈希校验、重装、空间不足、卸载入口、机型与内核选择、缺资源拒绝交接、退出与异常恢复 |
| 显示与输入 | 历史记录：Linux 实际运行几何 6 组合、EPDC 模拟 7 组合、单点 / Type A / Type B 输入 9 组合；另有 ASan / UBSan 检查 |
| 自主阅读 UI | 历史记录：真实 Qt 6 测试 20 项通过，无 QML 警告；审看 8 个界面。控制器使用测试数据 |
| ARM 程序 | 历史记录：DOOM、Neo Geo、设备探针和 Qt 客户端交叉编译成功；游戏为 Cortex-A8 / Linux 2.6.31 静态目标 |
| 游戏运行探针 | 历史记录：Cortex-A8 QEMU 下 DOOM、Neo Geo 探针成功，不刷新屏幕 |
| Qt 运行包 | PR #2 后已重新编译；自带 glibc 的 ABI note 为 Linux 3.0.0；历史 QEMU 文件、随机数、线程、计时器和 TLS 检查通过 |
| 网络 | 历史记录：同一 ARM 运行包加载随包 CA，访问 `https://ink.qq.com/` 返回 HTTP 200 |
| KPM 包钩子 | 安装与卸载仅增删 Ocean 的 5 个 Scriptlet；夹具验证保留 KOReader、账号和游戏数据 |
| Release 打包 | KPM `.kpkg`、安装 / 卸载 Scriptlet、ZIP 和 `SHA256SUMS` 的最小夹具冒烟测试通过 |
| 第三方来源 | 运行库按准确 Debian 包、字节哈希与对应源码核对，源码和许可随附件提供 |

显示测试模拟 ioctl 和输入事件，不会操作墨水屏。QEMU 使用电脑上的 Linux 内核，不能代替 Kindle 旧内核、触屏、休眠和账号实测。

| 机型 | 本轮硬件结果 |
| --- | --- |
| PW1 | 游戏 profile 待设备探针与实测；当前原生阅读器不支持 Linux 2.6.31 |
| PW2 / PW3 / Voyage | 预适配完成；PR #2 后的实际安装、扫码、翻页、游戏操作、退出、睡眠与重启后启动均待各型号验证 |

发行包的 `manifest.json` 保持 `hardwareValidation: pending`。最终 ZIP、KPM 包及源码附件的 SHA-256 见同一 Release 的 `SHA256SUMS`。
