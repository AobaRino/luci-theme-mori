# 开发与打包

## 仓库结构

```text
luci-theme-mori/
├── htdocs/luci-static/
│   ├── mori/                 # Mori 样式、图标、兼容资源和显示脚本
│   └── resources/menu-mori.js # 自带菜单模块
├── ucode/template/themes/mori/
│                             # LuCI ucode 模板
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
luci-theme-mori-0.1.0/
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

仓库包含符合 LuCI 目录布局的 `Makefile`，可放入与目标固件匹配、已准备好 LuCI feed 的 OpenWrt / ImmortalWrt SDK 或源码树中：

```sh
git clone https://github.com/AobaRino/luci-theme-mori.git package/luci-theme-mori
make menuconfig
make package/luci-theme-mori/compile V=s
```

在菜单中选择 `LuCI → Themes → luci-theme-mori`。构建系统根据固件分支生成其原生包格式，产物位于该构建树的 `bin/` 下。

主题登记由软件包的安装钩子显式运行 `/usr/libexec/mori-register`。此文件不放入 `uci-defaults`，以免触发软件包框架对其他配置草稿的全局提交；Mori 的安装钩子也不重载 rpcd。若将 Mori 直接编入固件镜像，首次启动后需运行 `sh /usr/libexec/mori-register` 登记主题，再到 LuCI 中选择 Mori。

这一配方与独立 `.tar.gz` 安装方式不同。独立安装包的检查结果不能代替完整 SDK 编译与对应 `.apk` / `.ipk` 安装验证；发布原生软件包前应实际完成该分支的构建和设备测试。

## 验证建议

针对改动选择实际页面检查：

- 外观：浅色、深色、桌面及窄屏，表格、输入框、动态列表、弹窗和错误提示。
- 导航：首页、网络接口、DHCP / DNS、系统页和至少一个第三方插件入口。
- 数据：首页刷新和隐藏来源区块后的摘要，实时流量图与图例。
- 安装：首次安装、升级、只登记、立即启用、未提交 LuCI 草稿与回退。

与运行中的路由器联调时，只更新主题文件及主题选项。不要为验证样式而修改网络配置、重启服务或提交其他页面遗留的草稿。

## 发布

1. 同步更新 `VERSION`、`Makefile` 的 `PKG_VERSION` 和必要的文档版本示例。
2. 运行检查及构建，核对归档内容和文件校验值。
3. 在目标固件验证实际界面、安装和回退，说明未覆盖的版本。
4. 检查待提交文件中没有凭据、会话、真实配置或私有设备截图。
5. 将源码推送到仓库；如发布安装包，再单独将已验证的归档及校验信息附到 Release。

源码提交、Release 附件和原生包测试是独立步骤。文档中不要将未实际生成或未测试的产物写成已经可用。

仓库的 GitHub Actions 会检查脚本语法、构建并校验独立安装包，成功后在对应运行中保留归档产物；此工作流不代替 SDK 原生软件包构建。
