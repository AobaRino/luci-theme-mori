# 安装、升级与回退

Mori 提供原生 `.apk` 和独立 `.tar.gz` 两种安装方式。通过包管理器安装后，应继续使用包管理器维护；独立安装器及其回退脚本不用于覆盖包管理器管理的文件。

## 支持环境

- 已运行 LuCI，且使用 ucode 模板运行时；设备上应存在 `/usr/share/ucode/luci/runtime.uc`。
- 可通过 SSH 以 root 身份登录，具备 `uci`、`ucode`、`sha256sum` 及 OpenWrt 常见 BusyBox 工具。
- 已验证的基础环境：ImmortalWrt 25.12.0、x86/64、LuCI `26.145.09311~a701807`。

旧版 Lua `.htm` 模板运行时不受支持。独立安装器会先检查环境、安装清单及模板，检查失败时应按提示处理，不要跳过检查强行安装。

## 原生 APK

原生包面向 ImmortalWrt 25.12.0 的 APK 包管理器。它使用官方 x86/64 SDK 构建，包内为架构无关资源，APK 元数据标为 `noarch`。这不代表其他架构、固件分支或旧版 `opkg` 系统已测试；不要将 `.apk` 交给 `opkg` 安装，也不要只修改后缀。

### 下载与校验

从同一个 [Release](https://github.com/AobaRino/luci-theme-mori/releases) 下载以下文件，保持文件名不变。以 v0.1.2 为例：

```text
luci-theme-mori-0.1.2-r1.apk
luci-i18n-mori-zh-cn-0.1.2-r1.apk
mori-sdk-signing-public.pem
APK-SHA256SUMS
```

`luci-i18n-mori-zh-cn-0.1.2-r1.apk` 为简体中文语言包（遵循 LuCI 标准 `luci-i18n-*` 形式），需要中文界面时一并安装。`APK-SHA256SUMS` 只校验上述 APK 和公钥。完整构建记录另外包含 SDK、feeds、源码提交、成品元数据、文件及脚本检查记录，适合需要核对构建来源时查看。

将文件上传到路由器 `/tmp/`。示例中的 `router.lan` 换成自己的路由器地址，密码由 SSH / SCP 交互输入：

```sh
scp -O luci-theme-mori-0.1.2-r1.apk luci-i18n-mori-zh-cn-0.1.2-r1.apk mori-sdk-signing-public.pem APK-SHA256SUMS root@router.lan:/tmp/
ssh root@router.lan
```

以下命令在路由器上执行：

```sh
cd /tmp
sha256sum -c APK-SHA256SUMS
MORI_KEYS="$(mktemp -d /tmp/mori-keys.XXXXXX)"
cp mori-sdk-signing-public.pem "$MORI_KEYS/"
apk --keys-dir "$MORI_KEYS" --no-network --repositories-file /dev/null verify /tmp/luci-theme-mori-0.1.2-r1.apk /tmp/luci-i18n-mori-zh-cn-0.1.2-r1.apk
apk --keys-dir "$MORI_KEYS" --no-network --repositories-file /dev/null add --no-commit-hooks /tmp/luci-theme-mori-0.1.2-r1.apk /tmp/luci-i18n-mori-zh-cn-0.1.2-r1.apk
```

每一步都应成功后再继续。公钥只用于上述命令的临时目录，不写入系统的 `/etc/apk/keys`；`--no-network` 和空软件源列表使这次操作只安装已上传的本地包。不要省略校验，或用 `--force-overwrite` 绕过文件冲突。若缺少依赖，先使用固件原有的可信软件源补齐提示的依赖，再重新安装 Mori。

`--no-commit-hooks` 跳过设备上额外的 APK 全局事务钩子，Mori 自身的安装及主题登记脚本仍会执行。

每个构建使用临时签名密钥，后续版本应下载对应 Release 的公钥，不能沿用上一个构建的公钥。

### 启用与升级

原生包安装默认只登记 Mori，保留当前主题选择。在 LuCI 的 **系统 → 系统 → 语言和界面** 中选择 Mori 后保存；先完成或放弃其他待应用设置。

如果安装输出提示 `registration deferred`，软件包可能已安装，但主题登记因现有 LuCI 草稿而延后。处理这些草稿后执行 `sh /usr/libexec/mori-register`，再刷新主题列表；脚本不会替你提交或丢弃草稿。

升级时获取新版本对应的 APK、公钥及校验文件，按相同流程校验后通过 APK 安装。安装脚本不全局提交 UCI 配置，也不重启网络、DNS、代理或 Web 服务。LuCI 的模块索引缓存可能由固件包框架刷新，这与服务重启不同。

### 安全卸载

在路由器 SSH 中执行：

```sh
sh /usr/libexec/mori-register --prepare-remove && apk del luci-theme-mori
```

准备命令会先检查 LuCI 草稿。如果 Mori 正在使用，它会在已登记且资源、模板有效的其他主题中选择备用主题，优先 Bootstrap，并只更新主题选择。存在草稿或没有可用备用主题时，命令会停止，后面的 `apk del` 不会执行。Mori 未在使用时，它在完成草稿检查后直接通过。

保留上述 `&&`。APK 的卸载前脚本返回错误不一定能阻止卸载，不能仅依赖包内钩子保护当前界面。包钩子会尽力准备备用主题，但直接执行 `apk del` 不能代替这个有条件的卸载流程。

### 从独立安装转交 APK 管理

先保留独立安装的备份，并确认没有未提交的 LuCI 设置。使用同版本、完整校验过的 APK 接管主题后，后续升级和卸载都改用 APK；不要再运行旧独立安装的回退脚本。

如果包管理器报告文件已由其他包持有或文件冲突，应停止并检查来源，不要强制覆盖。不同版本的独立安装和原生 APK 之间，不应在没有核对文件清单的情况下直接混合。

## 独立安装包

### 1. 在电脑上构建

需要 Python 3.10 或更新版本。安装 Node.js 后，检查脚本还会执行 JavaScript 语法检查。

```sh
git clone https://github.com/AobaRino/luci-theme-mori.git
cd luci-theme-mori
python3 scripts/build.py
python3 scripts/check.py
```

Windows 可使用 `py -3` 替代 `python3`。构建不依赖路由器上的原 Argon 安装，也不需要下载设备配置。

生成：

```text
dist/luci-theme-mori-0.1.2.tar.gz
dist/luci-theme-mori-0.1.2.tar.gz.sha256
```

从源码构建时，以当前 `VERSION` 和实际产物名称为准。若从仓库 Release 获取安装包，应同时获取对应的校验文件；没有附件时使用上述本地构建流程。

### 2. 上传并解压

将示例中的 `router.lan` 换成自己的路由器地址。密码由 SSH / SCP 交互输入，不应写入脚本或仓库。

```sh
scp -O dist/luci-theme-mori-0.1.2.tar.gz dist/luci-theme-mori-0.1.2.tar.gz.sha256 root@router.lan:/tmp/
ssh root@router.lan
```

`-O` 使用传统 SCP 传输，适用于未安装 SFTP 服务的 OpenWrt / ImmortalWrt。也可以用自己已有的文件传输工具将这两个文件放到路由器 `/tmp/`。

以下命令在路由器 SSH 中执行：

```sh
cd /tmp
sha256sum -c luci-theme-mori-0.1.2.tar.gz.sha256
tar -xzf luci-theme-mori-0.1.2.tar.gz
cd luci-theme-mori-0.1.2
```

### 3. 安装并启用

```sh
sh scripts/install.sh --activate
```

安装器会：

1. 校验完整文件清单、SHA-256 和 ucode 模板。
2. 检查是否存在未提交的 LuCI 设置。
3. 备份被替换的 Mori 文件及安装前的主题选项。
4. 安装资源，登记 `luci.themes.Mori`，并将 `luci.main.mediaurlbase` 设为 `/luci-static/mori`。

它不会重启设备或服务，也不会调用全局 UCI apply。网络、DHCP、DNS、防火墙和代理配置不属于主题安装范围。

安装成功后刷新后台页面。浏览器页签、登录页、侧栏及主题选项应显示 Mori。顶部按钮可切换明暗模式，选择仅保存在浏览器中。

#### 只安装，稍后再切换

```sh
sh scripts/install.sh
```

不带 `--activate` 时保留当前选中的主题。随后可在 LuCI 的 **系统 → 系统 → 语言和界面** 中选择 Mori；具体标签名称可能随翻译版本变化。页面保存前先处理其他待应用设置，避免一起应用无关改动。

如果安装器提示存在 LuCI 草稿，应先在对应页面完成或放弃这些修改，再重新运行。安装器不会代为清除草稿。

### 升级独立安装

构建或获取新版本，按相同步骤上传、校验并解压，再运行新版本的安装器。不要从源码仓库目录直接运行 `scripts/install.sh`，它需要构建产物中的 `rootfs/` 和校验清单。

每次成功安装都会创建独立备份。已经选中 Mori 时，即使升级不带 `--activate`，刷新后也会使用更新后的 Mori 资源。

固件大版本升级后应重新确认 ucode LuCI 兼容性。自定义主题文件是否随固件升级保留取决于固件升级方式，不由此安装器保证。

### 回退或移除独立安装

成功安装时终端会显示本次备份目录和完整回退命令，格式如下：

```sh
sh /root/mori-backups/<本次安装目录>/rollback.sh
```

将占位符替换为安装输出中的实际目录；执行备份目录里的脚本，不要执行源码或安装包内的裸 `rollback.sh`。

回退恢复本次安装前的受管文件及主题选项，不重启服务。首次安装的回退会移除本次新建的主题文件；升级的回退会恢复上一个版本。备份目录会保留。

回退会检查当前文件和主题选项是否仍与本次安装结束时一致，并在以下情况停止：存在未提交的 LuCI 设置、文件已被后续更新或手工编辑、主题选择已改变、或 Mori 已交由包管理器维护。它不会覆盖这些后续修改。

如果最初只安装而未启用 Mori，后来通过页面手动切换过主题，回退前需先恢复安装时保留的主题选择。多次升级应从最近一次安装的备份开始逐次回退，不能用旧备份覆盖新版本。

不要删除当前正在使用的主题文件。仅想暂时不用 Mori 时，在 LuCI 中选择其他已安装主题即可。

## 通过 SDK 构建原生软件包

仓库提供对应 ImmortalWrt SDK 的构建脚本与 `Makefile`，见[开发说明](DEVELOPMENT.md#sdk-软件包)。当前原生发布流程生成 `.apk`；没有宣称已构建或验证旧版 `.ipk`。

软件包安装默认只登记 Mori，不自动改变主题选择。删除软件包时使用上文的准备命令。独立安装包的回退脚本不用于撤销包管理器操作。

如果将主题直接编入固件镜像，请在首次启动后执行 `sh /usr/libexec/mori-register`，再在 LuCI 中选择 Mori。登记脚本会保留当前主题与其他配置。

## 常见问题

**提示需要 ucode LuCI**

确认固件使用 ucode 模板引擎。本主题不包含旧版 Lua 适配层，也不负责升级固件。

**提示安装清单或校验失败**

重新构建，或重新传输匹配版本的完整归档与校验文件。不要混合不同版本的模板、资源和清单。

**刷新后仍看到旧样式**

先确认已选择 Mori，再重新加载页面。构建会更新资源版本号；自行复制单个文件时，需要重新构建并安装完整版本。

**某个插件看起来与原生页面不同**

Mori 保留第三方插件自己的内容布局和专用控件规则，这是当前主题的范围边界。原生页面的兼容问题可在[仓库 Issues](https://github.com/AobaRino/luci-theme-mori/issues)反馈。
