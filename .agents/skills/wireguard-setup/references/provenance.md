# 来源、许可与验证界限

- [PinguIntel/kindle-wireguard](https://github.com/PinguIntel/kindle-wireguard)，已验证 tag v0.2.0；MIT，原文 [kindle-wireguard-MIT.txt](../licenses/kindle-wireguard-MIT.txt)。本 Skill 不提交上游预编译二进制，通过固定 Release 下载并校验。原版 ELF 保留为 kwg.bin，外面加按需加载 TUN 的 shell 包装。
- Amazon 5.13.6（373199 038）官方 GPL release；URL/SHA 在 profile。只提交头文件/Kconfig 的兼容补丁，不提交完整内核源码、镜像、固件或设备波形。内核派生补丁按 GPL v2，原文 [Linux-COPYING.txt](../licenses/Linux-COPYING.txt)。
- wireguard-go：MIT，由 kwg 上游依赖；此处未复制其实现。它的 TUN 初始化使用 IFF_TUN、IFF_NO_PI、IFF_VNET_HDR 和 TCP offload ioctls，探针据此检查。
- 本仓库新增脚本、探针与文档按仓库 MIT 许可；上游部分不因此改许可。发布包含 GPL 模块的二进制包时，还需按 GPL 提供对应源码/配置/补丁，不能只有一个 .ko。
- Pi Skill 布局遵循 [Agent Skills](https://agentskills.io/specification)。目录内 SKILL.md + 相对路径 assets/scripts/references；所有下载和测试输出放 build/。安装为全局 Skill 可使用指向这个已版本化目录的符号链接，避免两套副本漂移。

## 历史证据（不包含凭据）

| 层次 | 结论 |
| --- | --- |
| USB 文件复制与 SHA | 通过 |
| 原厂内核 TUN | 未启用；动态模块允许加载 |
| 模块编译/ABI | 通过；全部 78 个依赖为实际内核核心导出 |
| 真机 TUN ioctl | 通过；非持久接口自动移除 |
| 真机 WireGuard | 握手通过；已确认的电脑 VPN 节点 Ping 2/2 |
| 私钥导入 | 内部 0600 文件；USB 可见副本删除；未提交 |
| 当前测试隧道 | 测试结束已正常停止 |
| 自启服务模拟测试 | 15 项通过，不是真机证明 |
| 自启部署 | USB 文件已复制；启用/重启回读待验证 |
| KOReader 菜单实际启动 | 待验证 |
| SSH/SFTP / 文件传输 | 尚未配置/实测 |
| 长期稳定、休眠唤醒 | 待验证，不通过停 powerd 规避 |

Go 1.27 官方最低 Linux 3.2 的支持范围与这次 3.0.35 的成功实测要同时保留。不能宣称“所有 Go 1.27 程序都支持 3.0”，也不能抹掉实际成功结果。
