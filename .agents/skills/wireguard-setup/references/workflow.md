# 安装、回读与复现合同

本流程来源于一次真实 PW3 安装。它保留成功步骤，也保留未验证边界；不是“任意 Kindle 一键成功”。`scripts/bundle.py` 当前只接受已审核的 `pw3-5.13.6` 内核指纹。其他机型可运行只读 preflight，但不要修改指纹来绕过保护。

## 0. 工作区、能力与设备

AI 自行填写下列路径，不让用户填写型号/固件或粘贴私钥：

```sh
SKILL=/absolute/path/to/wireguard-setup
WORK=/absolute/path/to/project/build/wireguard-setup
umask 077
mkdir -p "$WORK/release"
# 新的专用工作目录内忽略所有缓存；不覆盖已有忽略规则。
if [ ! -e "$WORK/.gitignore" ] && [ ! -L "$WORK/.gitignore" ]; then
  printf '*\n' > "$WORK/.gitignore"
fi
```

- 要有本机下载、读写文件、执行命令能力。普通 USB 阶段无需 SSH。
- macOS 看 `/Volumes`，Linux 看 `/media`、`/run/media`；`bundle.py stage` 也可自动查找唯一 Kindle 挂载盘。多个设备再请用户选目标。
- 已越狱且有 Scriptlets；安装应用阶段需 KOReader。缺少这些基础时走当前 [KindleModding 向导](https://kindlemodding.org/jailbreak-wizard.html)，不要把无法运行入口当作程序不兼容。
- 保护已有插件、脚本、job 和用户书籍。复制器默认拒绝不同内容的既有文件。升级时先读差异、保存旧文件及哈希，只更新确认由本流程管理的文件，不要用整盘覆盖或 `git clean -fdx`。
- Kindle 没连接时只请用户插 USB 并进入文件传输模式。传配置时不要在工具输出、聊天、Git 或截图中展示私钥。

## 1. 预编译包：固定版本与校验

已验证上游：`https://github.com/PinguIntel/kindle-wireguard/releases/tag/v0.2.0`。

```sh
curl --fail --location --retry 1 \
  https://github.com/PinguIntel/kindle-wireguard/releases/download/v0.2.0/kwg.koplugin.zip \
  -o "$WORK/release/kwg.koplugin.zip"
```

先查看现有文件；若已存在且哈希正确，不重复下载覆盖。ZIP SHA-256 为 `fc759e7cc8b6f608f7cd92b3fd0b3b739bbb99660090e71e2740d6324225eac3`，二进制为 `9167c55f126cd6b74dbe3184b22a59fe1dc90c829754d0d5d0cf6eb731a6dee3`。渲染器会再次核对两者；校验失败停止，重新下载一次仍失败就报告，不改用不明二进制或源码构建。

GitHub API 限流时，可用固定 tag 的资产 URL 和已记录 SHA，不必依赖 `/latest`。需要更新上游版本时，另行审阅源码/运行要求、更新锁定哈希并重跑全部验证；不能直接让旧 Kindle 自动追最新 Go 构建。

本流程不依赖 KPM 中存在 `wireguard` 包。普通 KPM 官方源是否收录应现场查询，不编造 `;kpm install wireguard`。

## 2. 一次只读采集，减少 USB 往返

```sh
python3 "$SKILL/scripts/bundle.py" render preflight \
  --release-zip "$WORK/release/kwg.koplugin.zip" --out "$WORK/preflight"
python3 "$SKILL/scripts/bundle.py" stage "$WORK/preflight"
```

文件落在 `kwg-preflight/`，入口是 `documents/WireGuardCheck.sh`。这个入口先打印启动信息，采集完整内核配置、导出符号及原厂模块元数据，再执行官方二进制 `--help`；不载入模块，不改网络或电源管理。

macOS 写完并校验后：`diskutil eject "/Volumes/Kindle"`。请用户：**拔 USB → 点 WireGuard Check → 等 DONE/ERROR → 重新连接**。Linux 用对应的安全卸载操作。

回读并复制到私有 `$WORK/snapshot/`（或保留源结构再指定 snapshot 路径）：

- `kwg-preflight/launcher.log`
- `kwg-preflight/state/{status.json,check.log,runtime.log}`
- `kwg-preflight/tun-snapshot/*`

先确认日志是本次执行的新结果；可以比较执行前后的内容哈希/设备记录时间，不要仅凭文件存在。**没有 launcher.log 或没有状态文件，表示入口尚未成功执行，不等于兼容性检查失败。** 先核对文件、图书库入口及屏幕提示，再要求重试。

已验证设备观测：ARMv7；Linux `3.0.35-lab126`；`CONFIG_MODULES=y`、`CONFIG_MODVERSIONS=n`、`modules_disabled=0`；`CONFIG_TUN` 未启用。Go 1.27 二进制虽然超出官方 Linux ≥3.2 支持范围，但 `--help` 实测可运行。不要把“官方不支持”写成“现场已证实无法启动”，也不要把 `--help` 通过写成 VPN 可用。

## 3. 缺 TUN 时的分支

- 已有 TUN：核对它是否真的是可打开的字符设备及已注册驱动，不只看路径。其他新设备可按上游 README 安装原生插件；本技能的 PW3 模块与启动指纹不能套用过去。
- 没有 TUN：创建 `/dev/net/tun` 文件不会提供驱动。说明需要匹配内核模块；用户明确同意补装/开发后读 [tun-build.md](tun-build.md)。
- 不支持模块、被禁止加载、配置指纹不符、缺少所需导出符号、vermagic 不符：停止该路线，不 `insmod -f`、不改内核检查、不刷机。可另行提议 wireproxy 等免 TUN 方案，不擅自替换产品。

模块包的生成与复制：

```sh
python3 "$SKILL/scripts/bundle.py" render tun \
  --snapshot "$WORK/snapshot" --artifacts "$WORK/tun-build/artifacts" \
  --allow-kernel-module --out "$WORK/tun-package"
python3 "$SKILL/scripts/bundle.py" stage "$WORK/tun-package"
```

请用户安全弹出后点 **WireGuard TUN Test**，回读 `kwg-tun/state/`。只有 `moduleLoaded=true`、`tunIoctlsPassed=true` 且临时接口被移除，才继续。首次加载仍有内核异常风险；不设自启、不强制加载，失败停止。卡死超过一分钟可由用户长按电源约 40 秒重启后回读日志。

## 4. 导入配置与短时隧道测试

使用用户指定的本地配置文件，路径不要写进公开仓库。此自动路径仅支持一个 Peer、一个 IPv4 地址、一个私网 AllowedIPs CIDR；全局/复杂路由和 IPv6 需要另行审阅，不能偷偷降级。

先自动确认电脑是否已经加入用户的 VPN：macOS 可用 `route -n get <Kindle VPN IP>` 找接口，再看该接口的 IPv4 地址。不要把普通 Wi-Fi 网关误当 VPN 对端。只有已确认的自有 VPN 主机才传给 `--peer-test-ip`，否则省略，结果将记录 `not_requested` 而不是假装 Ping 通过。

```sh
python3 "$SKILL/scripts/bundle.py" render app \
  --snapshot "$WORK/snapshot" \
  --release-zip "$WORK/release/kwg.koplugin.zip" \
  --config "/path/to/user-selected/kindle.conf" \
  --peer-test-ip "<known-owned-vpn-ip>" \
  --include-private-config --out "$WORK/app-package"
python3 "$SKILL/scripts/bundle.py" stage "$WORK/app-package"
```

`--include-private-config` 明确将配置放入仅用于 USB 传输的 build/ overlay；若不传，不复制密钥。渲染目录设为 0700，文件设为 0600，但 FAT USB 盘不能依赖 Unix 权限，因此设备导入后删除 USB 可见副本。删除不是可抵抗取证的安全擦除；不要承诺已覆写闪存。

请用户：**拔 USB → Wi-Fi 开启 → 点 WireGuard Install Test → 等 DONE/CHECK LOG → 重新连接**。该测试：

1. 不碰已有隧道或正在运行的 managed job。
2. 校验 payload/config 后，原样导入 `/var/local/kwg/wg.conf`，必要时在内部保留旧配置备份。
3. 删除 USB 的 `kwg-install/client.conf`。
4. 用内部临时测试副本去掉 DNS、把 keepalive 设为 5 秒，只为快速发起握手。原配置不改写。
5. 测试握手及可选对端 Ping，随后终止自己的进程，检查接口已清理；不设自启。

回读 `kwg-install/state/status.json`、`tunnel.log`、`tunnel-status.txt`、`mac-ping.log`。成功必须有 `handshakeVerified=true`、`testCleanupSucceeded=true`、`wg0PresentNow=false`。Ping 需单列；握手成功但 Ping 无回应也可能是对端防火墙，不要伪造双向文件传输已成功。

## 5. 自启动、手动开关、重启证据

仅在用户同意后：

```sh
python3 "$SKILL/scripts/bundle.py" render service \
  --snapshot "$WORK/snapshot" --installed-root "/Volumes/Kindle" \
  --out "$WORK/service"
python3 "$SKILL/scripts/bundle.py" stage "$WORK/service"
```

服务包会校验现场已有程序和 TUN 文件；不是把不明文件覆盖到盘上。完整语义见 [service.md](service.md)。所有入口都会显示当前状态。

1. AutoStart On：验证文件，安装与 KOReader 完全一致的 kwg job，只为写 job 短暂挂载根文件系统可写，并恢复原模式；写内部 autostart 标记，启动服务。
2. 系统菜单真正重启；不要把休眠/唤醒算作重启。
3. 联网后只点 Status，不要先点 Start。检查 `CONNECTED`、`Autostart: ON`、`Reboot check: VERIFIED`。
4. 点 Stop 后再接 USB，回读 `kwg-service/state/boot-verification.json` 和当前 `status.json`。前者保留新 boot ID + framework_ready + TUN + 有效握手的证据；后者可以是 OFF，因为用户刚刚停止连接。

不要把“文件复制”“15 项模拟测试”“开机标记存在”混成重启自启已验证。

## 6. 状态判读与下一步

| 观测 | 结论/动作 |
| --- | --- |
| 没有启动日志/新结果 | 入口未执行或执行前失败，先核对点击，不判断硬件兼容性 |
| `tun_unavailable` / `CONFIG_TUN` 未启用 | 需要单独模块方案；不是再复制一次 kwg 就能解决 |
| `kernel_*_mismatch` / `module_*_mismatch` | 保留现场，停止加载；不能修改校验常量“修复” |
| `module_load_failed` / `tun_ioctl_probe_failed` | 回读 insmod、kernel、probe 日志；不强制加载、不设自启 |
| `tunnel_created_no_handshake` | 只说明本地接口创建；检查网络、服务端 Peer/公钥/AllowedIPs、端口 |
| `handshake_verified_test_stopped` | 临时 VPN 测试成功，当前已停止，不是自动运行中 |
| `WAITING_FOR_NETWORK` | 服务在等待 IPv4 网络，不强行打开 Wi-Fi或关休眠 |
| `TUN_RECOVERY_REQUIRED` | 自动重试已暂停；先看原因，手动 TUN Test 通过后再 Start |
| `UP_UNMANAGED` | 不杀未知隧道，不启动第二个实例 |
| `CONNECTED` + 新 boot ID + framework_ready + TUN ready | 本次新启动有自启证据；仍单列文件传输/长期稳定性 |

VPN 只提供网络路径。没有 SSH/SFTP 监听时不要宣称能传文件；这次历史现场没有启用 SSH/SFTP。需要时另行配置仅 VPN 内可达、密钥认证的服务，禁止顺手开放无密码 root SSH。
