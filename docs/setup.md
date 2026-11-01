# 设置 Kindle

## 安装

1. 已按 [KindleModding 官方向导](https://kindlemodding.org/jailbreak-wizard.html)完成越狱和越狱后设置，并具备 **KPM**。WinterBreak2 等现代越狱会预装 KPM；KindleModding 当前现代路径使用 KPM / Scriptlets。
2. 从[最新 Release](https://github.com/OceanJy333/kindle-hack/releases/latest)下载 `kindle-hack-ai-kit.zip` 和 `SHA256SUMS`。核对 ZIP 的 SHA-256 后解压，在发行包根目录运行安装命令；没有 Python 3 时，手动把 `kpm/*.kpkg` 复制到 Kindle 的 `ocean-kpm/`，把 `scriptlets/OceanKPMInstall.sh` 复制到 `documents/`。
3. 安全弹出 Kindle、拔 USB，点图书库中的 **Ocean KPM Install**。它会校验 `.kpkg`、调用 KPM 安装、注册 Ocean 启动项并执行设备检查。

复制后应有 `Kindle USB 根目录/ocean-kpm/ocean_*_kindlepw2.kpkg` 和 `Kindle USB 根目录/documents/OceanKPMInstall.sh`，不要多套一层 `kindle-hack-ai-kit/`。全程可保留原厂系统。想交给电脑上的 AI，直接复制[给 AI 的安装任务](给AI的安装任务.md)。

## 使用

| 图书库入口 | 操作 |
| --- | --- |
| Ocean Check | 识别设备、检查显示和输入、执行运行库探针，生成结果 |
| Ocean WeRead | 扫码登录自己的账号，打开书架和阅读器 |
| Ocean DOOM | 打开用户提供的 `games/doom1.wad` |
| Ocean Neo Geo | 打开用户提供的 `games/roms/mslug.zip`，同目录需有 `neogeo.zip`；匹配 FBA v0.2.97.29 |
| Ocean Stock | 结束应用并回原厂 |

以上 `games/` 路径都相对 Kindle USB 根目录。WAD、ROM 和 BIOS 不随发行包提供。程序保留原厂电源服务；按电源键休眠会结束当前应用，唤醒回原厂，需要时重新从对应 Scriptlet 打开。该行为待实机验证。

## 兼容检查

安装器自动读型号前缀、固件和内核，并选择 profile（设备配置）。显示和输入探针通过后才开放程序启动。

| 机型 | 结果范围 |
| --- | --- |
| PW1 | 独立游戏候选；必须通过设备本机的静态运行、显示和输入探针。Linux 2.6.31 无法运行当前最低要求 Linux 3.0 的 Qt 阅读器，报告 `reader_runtime_unavailable` |
| PW2、PW3、Voyage | 显示、触摸与运行库预适配；本轮包待各型号实机验证 |
| 未知 profile | 报告 `unsupported_device_profile`，保留探针信息 |
| profile 已知、内核不匹配 | 报告 `unsupported_kernel`；PW1 接受 `2.6.31`，PW2 / PW3 / Voyage 接受 `3.0.35`，均接受版本后缀 |

应用用 1072 × 1448 逻辑画布，按实际屏幕缩放；显示后端处理 8 / 16 bpp（每像素位数），触摸和 PagePress 翻页键按设备能力发现。预适配与探针结果不等于各固件实机通过。

## 检查结果

再次用 USB 连接 Kindle，打开 `ocean/state/status.json`。`reader`、`doom`、`neogeo` 分别报告各功能状态；`ready` 表示检查已通过，可以进行实测。状态与错误的固定处理见[给 AI 的安装任务](给AI的安装任务.md#状态与下一步)。

| USB 根目录下的位置 | 内容 |
| --- | --- |
| `ocean-kpm/` | 待安装的 `.kpkg` 包 |
| `kmc/kpm/packages/ocean/` | KPM 已解包安装的 Ocean 程序和公共 Qt 运行库 |
| `kmc/kpm/kpm.db` | KPM 安装记录 |
| `ocean/state/status.json` | 最近一次设备检查结果 |
| `ocean/state/device.json`、`probe.json`、`probe.log` | 设备识别、显示、输入和静态运行探针 |
| `ocean/state/reader-probe.json`、`reader-probe.log` | Qt 本地运行检查 |
| `ocean/state/doom-probe.log`、`neogeo-probe.log` | 游戏静态运行检查 |
| `ocean/state/session.json`、`app.log`、`sleep.log` | 最近一次应用会话、退出和休眠事件 |
| `ocean/state/weread/` | 阅读器账号和本地状态 |
| `weread-offline/` | 离线书库 |
| `games/` | 使用者提供的游戏数据、配置和存档 |

设备侧这些路径位于 `/mnt/us/` 下。KPM 卸载删除 `kmc/kpm/packages/ocean/` 和 Ocean 启动项，保留 `ocean/`、`weread-offline/` 和 `games/`。

## 电脑命令

电脑有 Python 3 时，在解压后的发行包根目录运行；USB 路径由操作 AI 自行识别。macOS 示例：

```sh
python3 install.py install --kindle /Volumes/Kindle --json
python3 install.py verify --kindle /Volumes/Kindle --json
python3 install.py status --kindle /Volumes/Kindle --json
```

Windows 可用 `py -3` 代替 `python3`，`--kindle` 使用实际盘符。`verify` 检查 `.kpkg` 与安装 Scriptlet 的哈希；它不替代 Kindle 上的 KPM 安装和设备检查。源码工作区的同一入口为 `python3 installer/install.py`，需要已通过 `tools/package-release.py` 组装的完整 Release。

电脑卸载命令会复制 **Ocean KPM Uninstall** 到图书库；安全弹出后在 Kindle 上点开它，由 KPM 执行卸载：

```sh
python3 install.py uninstall --kindle /Volumes/Kindle --json
```

## 实测

设备检查通过后，逐项记录实际结果：阅读器扫码、开书、翻页、返回；游戏开始、触摸操作、退出；电源键休眠后唤醒；重启后再次从对应 Scriptlet 打开。手机与 Kindle 的阅读进度同步、离线阅读等功能分别实测。文件复制、KPM 安装、探针通过和设备实测分开报告。

源码构建、旧私有运行包和 Voyage 独立系统见 [BUILD.md](../BUILD.md)。
