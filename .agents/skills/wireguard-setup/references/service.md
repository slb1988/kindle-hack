# Kindle WireGuard：自启动与手动控制

适配当前 PW3 / 固件 5.13.6（373199 038），与 KOReader 插件共用 `kwg` Upstart 服务，不另外启动第二个 VPN。

## 图书库入口

- **WireGuard AutoStart On**：校验文件，安装 `/etc/upstart/kwg.conf`，启用开机自启动，并启动服务、显示状态。
- **WireGuard Start**：手动开启；已经运行时不会重复启动；最后显示状态。
- **WireGuard Stop**：只停止当前服务；不取消下次开机自启；最后显示状态。
- **WireGuard Status**：查询当前状态并保存公开状态快照，不启动或停止 VPN。
- **WireGuard AutoStart Off**：关闭以后开机自启，不中断当前连接；要立即断开，再点 Stop。

## 状态说明

- `CONNECTED`：隧道在运行，最近 240 秒内有握手。仍应结合握手时间判断；这不是每次查询都 Ping 对端。
- `WAITING_FOR_NETWORK`：服务已启动，等待 IPv4 网络；不会强行打开 Wi-Fi。
- `STARTING` / `LOADING_TUN` / `WAITING_FOR_HANDSHAKE`：正在准备驱动或连接。
- `STALE_HANDSHAKE`：接口仍在，但握手已旧，不能当作当前可达。
- `OFF`：服务已停止。
- `TUN_RECOVERY_REQUIRED`：上次 TUN 加载失败或中断；自动加载已暂停，避免连续重启。查看日志并运行原来的 WireGuard TUN Test；通过后再点 Start。
- `UP_UNMANAGED`：发现了不由本服务管理的隧道，不会擅自杀掉它。
- `PAYLOAD_ERROR` / `CONFIG_ERROR`：程序校验或配置错误，不会盲目执行或覆盖配置。

输出包含 Autostart、Service、Network、TUN、VPN IP、Handshake、RX/TX 和 Reboot check。不会显示私钥。

## 持久化与回滚

程序与模块仍在 `/mnt/us/koreader/plugins/kwg.koplugin/`、`/mnt/us/kwg-tun/`；配置仍在内部的 `/var/local/kwg/wg.conf`，没有重写私钥。

新增控制脚本在 `/mnt/us/kwg-service/`。开机事件 `framework_ready` 触发同一个 kwg 服务；等待网络后校验并按需加载 TUN，再启动隧道。Wi-Fi 丢失或默认路由变化时，先正常结束子进程，再等待重连。Stop 会把终止信号转发给 VPN 子进程，以便其退出时恢复 DNS。

只在安装 Upstart 文本任务时短暂写入根文件系统，然后恢复原先只读状态；不刷写内核、固件或分区，不停止原厂 powerd、不禁用休眠。休眠断 Wi-Fi 时设备仍会离线。

若想回到完全手动：先点 AutoStart Off，再点 Stop。保留 job 文件让手动 Start 仍可用。不要删除 `kwg-tun/`，否则重启后将缺少按需加载的模块。

## 真机重启验证

1. 拔 USB、保持 Wi-Fi 开启，点击 AutoStart On，查看状态。
2. 从 Kindle 菜单真正重启，不只是按电源休眠。
3. 等 Wi-Fi 连接后点击 Status，不要先点 Start。
4. 看到 `VPN: CONNECTED`、`Autostart: ON` 和 `Reboot check: VERIFIED` 后，再点 Stop，然后连接 USB。

Status 会比较安装时的 boot ID 和本次 boot ID，并检查服务是否由 `framework_ready` 自动启动。新启动且 TUN/握手通过时会保留 `boot-verification.json`；之后手动 Stop 不会覆盖这份成功证据。停止后再插 USB，可避免运行中的程序占用用户存储。

公开回读文件：`kwg-service/state/status.json`、`status.txt`、`boot-verification.json`、`service-start.json`。它们是按钮点击时的快照，不是 USB 模式下实时联网的证明。

本地隔离模拟测试已覆盖启停、自启开关、重复启动防护、网络重连、退出清理和加载中断保护；真机启用与重启验证需回读设备结果，不能以模拟测试代替。
