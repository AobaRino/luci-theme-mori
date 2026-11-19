# 开发与打包

## 仓库结构

```text
luci-theme-mori/
├── htdocs/luci-static/
│   ├── mori/                 # Mori 样式、图标、兼容资源和显示脚本
│   └── resources/menu-mori.js # 自带菜单模块
├── ucode/template/themes/mori/
│                             # LuCI ucode 模板
├── po/                       # LuCI i18n 翻译目录（构建为 luci-i18n-mori-* 语言包）
├── root/usr/libexec/        # 原生软件包显式调用的主题登记脚本
├── scripts/                 # 检查、构建、独立安装与回退
├── docs/
├── Makefile                 # OpenWrt / ImmortalWrt SDK 配方
├── VERSION
├── LICENSE
└── THIRD_PARTY_NOTICES.md
```

`dist/` 为本地构建产物，不应将路由器备份、部署日志、凭据或真实网络截图放进源码目录。

## 本地检查与独立安装包

构建使用 Python 3.10 或更新版本的标准库，不需要额外 Python 或 npm 包。JavaScript 语法检查使用 Node.js；未安装 Node.js 时检查脚本会明确提示跳过此项。

```sh
python3 scripts/build.py
python3 scripts/check.py
```

Windows 可使用 `py -3` 替代 `python3`。构建脚本从本仓库源码生成安装目录和归档，不从任何路由器采集文件。

生成的安装目录包含：

```text
luci-theme-mori-0.1.1/
├── rootfs/                  # 准备复制到路由器的资源与模板
├── scripts/install.sh
├── scripts/rollback.sh
├── VERSION
├── manifest.sha256         # 相对于 rootfs 的文件校验值
├── README.md
├── LICENSE
├── THIRD_PARTY_NOTICES.md
└── docs/                    # 安装、开发说明与公开预览图
```

构建会为主题资源生成基于内容的版本号，避免更新后继续使用旧缓存。修改资源后应重新构建，不能只替换归档中的某个文件而继续使用旧清单。

模板中的资源指纹随构建同步更新，更新后的模板也应纳入源码提交。修改 CSS、JavaScript、图标或版本号后，请在提交前运行 `build.py` 和 `check.py`；SDK 直接使用仓库内已经同步指纹的模板。

## 页面边界

菜单、权限、状态请求以及配置保存和应用由 LuCI 提供。Mori 的脚本只处理界面外观和现有状态信息的呈现。

原生页面使用精确的页面名单应用内容样式；第三方页面只复用外壳。增加原生页面支持时，应先核对对应固件中的路由和实际 DOM，再加入名单，避免用宽泛前缀覆盖插件。

首页摘要读取原生状态区块已经加载的数据。移动区块时保留原节点和事件处理；不要复制状态值、另建定时请求或将未获取的数据填成零。

修改明暗模式时，需要同时检查继承的兼容样式与 Mori 的覆盖规则。动态列表的移除目标由原生组件的伪元素实现，不能仅为更换图标而移除原生事件目标。

## SDK 软件包

原生发布构建固定使用 ImmortalWrt 25.12.0 的 x86/64 SDK 和该版本公布的 feeds 提交，不跟随 feeds 的浮动分支。

| 输入 | 固定值 |
| --- | --- |
| SDK | `immortalwrt-sdk-25.12.0-x86-64_gcc-14.3.0_musl.Linux-x86_64.tar.zst` |
| SDK SHA-256 | `c228059aa1e58c3b3ae58ce8dcc7549fd08379d8e231daf80fcca15b677564cb` |
| LuCI feed | `a701807e2e0051f342f9980fd85f90f6966af9b0` |
| Packages feed | `881bc2200a61801edc8db88e7631f7e6468989a1` |

来源：[官方 SDK 目录与校验值](https://downloads.immortalwrt.org/releases/25.12.0/targets/x86/64/)、[feeds.buildinfo](https://downloads.immortalwrt.org/releases/25.12.0/targets/x86/64/feeds.buildinfo)。

在 Linux x86_64 构建主机上运行：

```sh
sh scripts/build-sdk.sh
sudo sh scripts/test-native.sh
```

所需主机工具与软件包见 [SDK 工作流](../.github/workflows/build-sdk.yml)。也可在 GitHub Actions 手动运行 **Build native SDK package**；成功产物名为 `luci-theme-mori-native-sdk`。

构建脚本先校验 SDK 和 `feeds.buildinfo` 的 SHA-256，再使用锁定提交构建 Mori。`MORI_SDK_JOBS` 可调整并行数，默认 2；`MORI_SDK_WORKDIR` 指定临时工作目录的父目录。脚本只创建和清理自己命名的临时子目录，不删除指定父目录。输出目录 `dist/sdk/` 必须为空，重建前应先将上次产物另行保存。

输出包括：

- `luci-theme-mori-0.1.1-r1.apk`、`luci-i18n-mori-zh-cn-0.1.1-r1.apk` 与 `mori-sdk-signing-public.pem`。
- `APK-SHA256SUMS`：仅用于用户安装时校验上述 APK 和公钥。
- `SHA256SUMS`：整个 SDK 产物目录的完整校验清单。
- `provenance.json`、`feeds.buildinfo`、`feeds.conf` 和 `sdk.config`：固定输入及构建来源。
- `package-metadata.yaml`、`i18n-zh-cn-metadata.yaml`、`payload-sha256.txt`、`i18n-zh-cn-payload-sha256.txt`、`payload-verification.txt`、`signature-verification.txt`、`hooks/` 和 `native-smoke-test.txt`：成品及测试记录。

SDK 构建使用临时签名私钥，只保留公钥作为验证材料，私钥不进入产物或仓库。因此固定的 SDK、feeds 和源码可用于核对构建输入及安装内容，但不同构建的签名和 APK 文件哈希不承诺逐字节相同。发布时应上传实际完成测试的那个 APK。

仓库同时包含符合 LuCI 目录布局的 `Makefile`，也可放入与目标固件匹配、已准备好 LuCI feed 的 SDK 或源码树中：

```sh
git clone https://github.com/AobaRino/luci-theme-mori.git package/luci-theme-mori
make menuconfig
make package/luci-theme-mori/compile V=s
```

在菜单中选择 `LuCI → Themes → luci-theme-mori`。当前固定 SDK 生成 `.apk`，包的架构字段为 `noarch`；这是资源包的架构标识，不能据此宣称所有固件和设备已验证。旧版 `.ipk` 构建不在当前发布验证范围内。

主题登记由软件包的安装钩子显式运行 `/usr/libexec/mori-register`。此文件不放入 `uci-defaults`，以免触发软件包框架对其他配置草稿的全局提交；Mori 的安装钩子也不重载 rpcd。若将 Mori 直接编入固件镜像，首次启动后需运行 `sh /usr/libexec/mori-register` 登记主题，再到 LuCI 中选择 Mori。

原生包包含固件框架生成的安装及卸载包装脚本，检查源码中的 `Makefile` 不足以验证最终行为。发布前还应检查成品 APK 的元数据、文件清单和实际脚本，在隔离的同版本根文件系统执行安装与卸载，再对目标设备进行安装验证。

APK 的卸载前脚本错误不能被当作可靠的阻止机制。支持的用户卸载入口是 `mori-register --prepare-remove && apk del luci-theme-mori`：先完成草稿检查和备用主题选择，再进入 APK 卸载。修改这一流程时应同时验证无备用主题和存在草稿的失败路径。

## 验证建议

针对改动选择实际页面检查：

- 外观：浅色、深色、桌面及窄屏，表格、输入框、动态列表、弹窗和错误提示。
- 导航：首页、网络接口、DHCP / DNS、系统页和至少一个第三方插件入口。
- 数据：首页刷新和隐藏来源区块后的摘要，实时流量图与图例。
- 安装：首次安装、升级、只登记、立即启用、未提交 LuCI 草稿与回退。

与运行中的路由器联调时，只更新主题文件及主题选项。不要为验证样式而修改网络配置、重启服务或提交其他页面遗留的草稿。

## 发布

[Release Mori 工作流](../.github/workflows/release.yml) 在推送 `vX.Y.Z` tag 后自动构建、测试并发布。它要求 tag 去掉 `v` 后与 `VERSION`、`Makefile` 中的 `PKG_VERSION` 完全一致，`PKG_RELEASE` 为正整数。当前自动发布只接受正式版本，例如 `v0.1.1`；不匹配的 tag 会在下载 SDK 前失败。

发布新版本时：

1. 更新 `VERSION`、`Makefile` 的 `PKG_VERSION`、包修订号及必要的文档示例。
2. 运行 `python3 scripts/build.py` 和 `python3 scripts/check.py`，提交更新后的模板资源指纹及版本文件。
3. 确认提交中不包含凭据、设备配置或私有截图。涉及界面及固件兼容性的改动，应补充目标设备上的实际验证。
4. 先将版本提交推送到默认分支 `main`，再为该提交打 tag 并推送。以下以源码已更新到 `0.1.1` 为例：

```sh
git push origin main
git tag -a v0.1.1 -m "Mori v0.1.1"
git push origin v0.1.1
```

在 [Actions](https://github.com/AobaRino/luci-theme-mori/actions/workflows/release.yml) 查看 **Release Mori**。流程依次执行：

1. 核对 tag、源码版本和当前提交。
2. 并行运行源码/脚本检查、独立安装器与发布保护测试，以及固定 SDK 构建、签名和文件审计、官方隔离 rootfs 中的安装/升级脚本/卸载测试。
3. 下载本次运行通过测试的产物，复核校验值、源码提交及文件清单，组装发布附件。
4. 再次确认远程 tag 指向受测提交，创建 Release 草稿、上传附件并核对 GitHub 返回的每个附件 SHA-256 和大小。
5. 附件全部一致后将草稿公开为正式 Release。

自动发布包含 8 个附件：原生主题 APK、简体中文语言包 APK（`luci-i18n-mori-zh-cn`）、公钥、`APK-SHA256SUMS`、独立安装包及其校验文件、SDK 验证归档及其校验文件。原生包上传的是本次测试完成的同一份文件，不在发布阶段重新构建或签名。

构建和测试 job 只有仓库读取权限；只有最后的发布 job 使用内置 `GITHUB_TOKEN` 的 `contents: write` 权限，无需配置 PAT 或路由器凭据。CI 不连接实际路由器，也不将隔离测试写成实机验收。`docs/VALIDATION.md` 是 v0.1.0 的历史实机记录；后续版本的自动测试记录随各自附件提供。

### 手动试跑与失败重试

可在 **Release Mori → Run workflow** 选择分支进行试跑，或运行：

```sh
gh workflow run release.yml --ref main
```

手动运行会完成相同的版本检查、构建、测试及附件组装，并上传 `luci-theme-mori-release-bundle` Actions artifact；它始终跳过 Release 发布，即使选择了 tag 也不会发布。

任一检查失败都不会公开新 Release。上传过程中失败可能留下草稿；在同一次 Actions 运行中选择 **Re-run failed jobs**，发布 job 会继续使用原产物，只补传缺失附件。相同的草稿或已发布 Release 必须与本次提交、附件清单及校验值完全一致，否则停止，不覆盖现有附件。

不要通过强制移动已发布 tag 更新版本。完整重跑 SDK 会产生新的临时签名，因此与旧草稿的附件可能不同；遇到冲突时先检查失败日志及草稿，确认后处理未完成草稿或发布新版本，不能用强制覆盖跳过校验。
