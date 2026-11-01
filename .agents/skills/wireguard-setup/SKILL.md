---
name: wireguard-setup
description: 给已越狱 Kindle 安装、修复 WireGuard/kwg，检查和补齐 TUN，配置开机自启及手动启停/状态入口。用户提到 Kindle VPN、tun.ko、重启后自动连接或复现本次安装流程时使用；包含已验证的 PW3 5.13.6 模块构建路线与安全清理方法。
compatibility: 需要本地文件/命令能力、Python 3.12+、USB 可写及 Kindle Scriptlets/KOReader。普通安装用预编译包；Docker 和 Zig 0.15.2 仅用于明确授权的 TUN 开发。
---

# Kindle WireGuard Setup

先说明使用本 Skill。**这是 WireGuard 专项，不要误跑 Ocean/微信读书安装器。** 所有相对路径按本文件所在目录解析；下载、渲染、测试、设备快照都放到 Git 忽略的 `build/wireguard-setup/`，不要写进 Skill 源码目录。

## 先读与边界

1. 完整阅读 [workflow.md](references/workflow.md)；自启动/状态问题同时阅读 [service.md](references/service.md)。
2. 缺 TUN 时先只读检查。只有用户明确要求补装/开发 TUN，才进入 [tun-build.md](references/tun-build.md)。不自行刷内核、改分区、停 powerd、禁用休眠、强制 `insmod -f`，也不套用别的固件的 `.ko`。
3. 当前可自动复现的模块 profile 只有 [pw3-5.13.6.json](profiles/pw3-5.13.6.json)。以**运行内核配置和编译版本的 SHA-256**匹配，不只看商业型号或 `uname -r`。其他设备先探测，报告未验证，不改 profile 绕过检查。
4. 程序安装、TUN/隧道实测、KOReader 菜单、真机重启自动启动、SSH/SFTP 文件传输分别报告。历史记录：TUN、握手和对端 Ping 已实测通过；自启动只有 15 项隔离模拟测试及 USB 复制，**真机启用/重启仍待回读**，不可沿用模拟成功作为实机证明。

## 执行顺序

- **识别 USB**：自行检查挂载点；缺设备才请用户插 USB，多台才请用户选目标。不先索要型号、固件、SSH 信息。
- **校验预编译 Release**：复现默认固定 `PinguIntel/kindle-wireguard v0.2.0`；URL、ZIP/二进制 SHA-256 在 profile 中。不要自动升级为未经旧内核测试的最新版，不因普通安装失败自动构建 Go 程序。
- **一次采集**：`scripts/bundle.py render preflight` 同时准备可见的 `WireGuard Check`、完整内核配置/导出符号采集及 `kwg --help`。复制≠执行。没有 `launcher.log`/结果文件时先查入口是否真正运行，不宣称内核不兼容。
- **TUN 分支**：已有可用 TUN 可按上游安装。`CONFIG_TUN` 未启用不能只靠 `mknod`；明确授权后按专门文档构建匹配模块，只手动临时加载并运行完整 ioctl 探针，通过后才启用 VPN。
- **导入与短测**：使用用户指定的配置文件，绝不输出私钥。已验证脚本只支持单 peer、单 IPv4 私网网段的分流测试；不擅自把全局 VPN 配置改成分流。临时测试副本不改 DNS，并快速发起握手；原配置原样导入 `/var/local/kwg/wg.conf`（0600），删除 USB 可见副本。可选 Ping 目标必须是已确认的自有 VPN 节点，禁止扫描。
- **持久化**：用户同意后部署 service 包，使用与 KOReader 相同的 `kwg` Upstart job。保留 Start、Stop、Status、AutoStart On/Off；所有操作显示状态。已有不同 job 不覆盖。手动 Stop 不取消自启，AutoStart Off 不停止当前隧道。
- **真机验证**：AutoStart On → 系统菜单重启 → 联网后只点 Status（不要先点 Start）。必须同时观察新 boot ID、`framework_ready` 来源、TUN ready 和有效握手。保存 `boot-verification.json`；之后可 Stop 再接 USB，避免运行程序占用用户存储。
- **归档清理**：按 [artifacts.md](references/artifacts.md) 先保存/校验少量证据和恢复包，再删可重新下载/生成的源码与临时目录。不要清理 Kindle 上的运行目录，不要全局 `git clean -fdx` 或 `docker system prune`。

## 工具

- `scripts/bundle.py`：校验 profile、保护密钥、渲染 USB overlay、校验复制。默认拒绝覆盖不同文件；遇到升级冲突先查看差异、备份，仅替换确认属于本流程的文件。
- `scripts/prepare_tun.py`：校验官方 GPL 包并应用精确补丁，只准备模块构建输入，不刷机、不加载模块。
- `tests/test_bundle.py`：不需要设备的配置、模板及复制保护测试。
- `tests/test_service.py --bundle WORK/service --image IMAGE`：隔离 Docker 中的 15 项服务测试；输出留在 WORK，成功后删除测试夹具。

具体可执行命令、需要用户点击的入口、错误分支见上述 references。只有实体操作交给用户；文件下载、校验、复制、回读由 AI 完成。

## 交付

简述安装位置/版本、模块 ABI 与 ioctl 结果、握手/Ping、当前状态时间、自启开关、重启证据，以及 SSH/SFTP 是否完成。`CONNECTED` 是“接口存在且最近握手有效”，不是每次都实时 Ping；USB 上的 JSON 是按钮点击时的快照。休眠断 Wi-Fi 时仍会离线。
