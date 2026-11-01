# 仅构建匹配的 TUN 模块

**需要用户明确授权补装/开发 TUN。** 这是原厂系统上的独立模块，不是新系统或刷内核任务。只用运行内核的配置和导出符号；不能把本 profile 的 `tun.ko` 给别的固件试着强行加载。

## 已验证 profile

- PW3；固件 `5.13.6 (373199 038)`；`3.0.35-lab126`；`armv7l`。
- `CONFIG_MODULES=y`、`CONFIG_MODULE_UNLOAD=y`、`CONFIG_MODVERSIONS=n`、非 SMP、PREEMPT、ARMv7 p2v8。
- 实际 vermagic：`3.0.35-lab126 preempt mod_unload ARMv7 p2v8 `（末尾有空格）。
- SHA 指纹和官方 GPL 来源在 [profile](../profiles/pw3-5.13.6.json)。
- 官方包：`Kindle_src_5.13.6_3731990038.tar.gz`，332,761,879 bytes，SHA-256 `4a01245d1bf8724da428dd044bd0e2f6cae0687446b3a2c909dc21a7acc2222f`。
- 不同机型的“5.13.6”有不同构建号。不要只按固件版本拼下载 URL。常见 `katadelos/linux-3.0.35-lab126` 镜像来自 **5.10.1.1**；这次选择了精确对应的 5.13.6 官方包，而非沿用较旧源码。

## 输入与准备

先回读 `kwg-preflight/tun-snapshot/`，放到私有 `$WORK/snapshot`。至少包括：
`runtime-kernel.config`、`runtime-kallsyms.txt`、`kernel-version.txt`、`kernel-release.txt`、`architecture.txt`、`stock-module-metadata.txt`。

```sh
python3 "$SKILL/scripts/prepare_tun.py" \
  --snapshot "$WORK/snapshot" --work "$WORK/tun-build" \
  --allow-kernel-module
```

可通过 `--archive /path/to/already-downloaded.tar.gz` 复用已校验下载。准备器校验大小/SHA，使用 Python 3.12+ 的 tar data filter，应用精确补丁并建立空 `.scmversion`。不执行任何设备命令。输出目录非空时拒绝覆盖。预留至少约 2 GiB 可用空间；Docker 镜像另计，磁盘紧张时先清理旧源码。

## 编译：只要 modules，不要 uImage/zImage

```sh
IMAGE=wireguard-tun-build:pw3
docker build -t "$IMAGE" -f "$SKILL/assets/tun/Dockerfile" "$SKILL/assets/tun"
docker run --rm --network none --cap-drop ALL --cpus 2 --memory 2g \
  --entrypoint /bin/sh -v "$WORK/tun-build:/work" "$IMAGE" /work/build-inner.sh \
  > "$WORK/tun-build/build.log" 2>&1
```

现成的、经检查工具链一致的本地 image 可以复用；历史现场复用了 `kindle-ocean-build-src`。不要为了本任务删除其他项目的容器或镜像。

构建脚本会：
1. 复制实际配置，只将 `CONFIG_TUN=n` 改为 `m`。
2. `oldnoconfig` 后比较完整配置，必须只有这一项差异。
3. `modules_prepare`，不生成内核镜像。
4. 在 **MODVERSIONS 确认关闭** 的前提下，用这台机器的实际 `__ksymtab_*` 导出名限制 modpost；CRC 不参与该内核的模块校验。若 MODVERSIONS 开启则停止，不能照抄零 CRC。
5. 构建外部 `tun.ko`，只 strip debug，不 strip 全部模块符号。
6. 比较 vermagic，并要求所有导入符号都由实际内核核心导出。历史实测是 78 个、缺失 0、外部模块依赖 0；不要伪造导出表来消除 undefined symbol。
7. 写 `artifacts/build-manifest.json`，其中实机字段仍为 false。编译成功不是加载成功。

## 已踩过的编译坑

补丁在 [source-compat.patch](../assets/tun/source-compat.patch)，驱动 `tun.c` 本身未改：

- GPL 包省略了私有 REAGL 的 Kconfig 定义，但运行配置含 `CONFIG_FB_MXC_EINK_REAGL=m`。恢复这个声明，仅为保留原配置/头文件条件；不是编译或替换显示驱动。不能直接忽略配置差异断言。
- 老内核只认识旧 GCC 头文件版本，需要兼容现代 GCC 属性判断。
- `arm-linux-gnueabihf-gcc` 在老 Kbuild 的选项探测中可能退回 ARMv5，出现 ldrex/strex/cpsid 不支持。构建参数明确指定 ARMv7-A、Cortex-A9、soft-float、ARM mode。
- 新 GCC 会把 `put_user` 中 const 的固定寄存器变量折叠到错误寄存器，触发 `.ifnc r3,r2; .err`。仅去掉该寄存器变量的 const，让 r2 约束成立；**不能删除汇编断言**。
- `.scmversion` 必须为空，避免父 Git 仓库导致 release 末尾多出 `+`，从而破坏 vermagic。
- 用户态探针不能用要求 Linux ≥3.2 的新 glibc 静态程序来测试这个 3.0 内核。使用 Zig 0.15.2 的静态 musl soft-float ARM 目标。

## 编译小探针并渲染临时加载包

```sh
# ZIG 由 AI 定位已校验的 Zig 0.15.2；不要让用户复制未知二进制。
"$ZIG" version
"$ZIG" cc -target arm-linux-musleabi -mcpu=cortex_a9 -O2 -static -s \
  -Wall -Wextra -Werror "$WORK/tun-build/tun-probe.c" \
  -o "$WORK/tun-build/artifacts/tun-probe"

python3 "$SKILL/scripts/bundle.py" render tun \
  --snapshot "$WORK/snapshot" --artifacts "$WORK/tun-build/artifacts" \
  --allow-kernel-module --out "$WORK/tun-package"
python3 "$SKILL/scripts/bundle.py" stage "$WORK/tun-package"
```

探针先检查字符设备 major/minor，再测 TUNGETFEATURES、TUNSETIFF、TUNGETIFF、TCP offloads、virtio header size，最后关闭并确认临时接口消失。不分配 IP、不改路由/DNS、不发包。没有 ARM 模拟器时，明确写未模拟；设备加载器先运行 helper `--help`，能启动后才尝试 insmod。

设备加载脚本校验运行配置、内核编译版本、模块/helper SHA、vermagic、模块加载开关；只普通 insmod，不 force。仅在驱动注册后才补建 `/dev/net/tun`，只给 root 权限。失败时只尝试卸载本次自己加载的模块，不强制移除别人的驱动。

请用户点 **WireGuard TUN Test** 后回读结果。成功判据为：
`result=ready_temporary`、`moduleLoaded=true`、`tunIoctlsPassed=true`、`interfaceRemoved=true`。
重复点击后 `moduleAlreadyLoaded=true` 正常，但不能因此伪造“本次刚刚 insmod 成功”。按实际字段报告。

首次试验不设自启。真机通过后再安装 VPN；最后用户同意才启用开机自动加载。所有内核、固件、引导器、分区刷写都不在此流程内。
