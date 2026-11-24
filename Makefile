# SPDX-License-Identifier: Apache-2.0
include $(TOPDIR)/rules.mk

PKG_NAME:=luci-theme-mori
PKG_VERSION:=0.1.2
PKG_RELEASE:=1
PKG_PO_VERSION:=$(PKG_VERSION)-r$(PKG_RELEASE)
PKG_LICENSE:=Apache-2.0
PKG_LICENSE_FILES:=LICENSE

LUCI_TITLE:=Mori - a calm, modern LuCI theme
LUCI_URL:=https://github.com/AobaRino/luci-theme-mori
LUCI_MAINTAINER:=AobaRino
LUCI_DEPENDS:=+luci-base +ucode +ucode-mod-uci +ucode-mod-fs
LUCI_PKGARCH:=all
# Keep audited source templates and custom-property CSS unchanged by the SDK.
LUCI_MINIFY_UT:=0
LUCI_MINIFY_CSS:=0
LUCI_MINIFY_JS:=0

# Override luci.mk's default postinst: Mori does not need an rpcd reload.
# The helper deliberately lives outside /etc/uci-defaults so OpenWrt's
# generic postinst does not run a global `uci commit` before this handler.
define Package/luci-theme-mori/postinst
#!/bin/sh
[ -n "$${IPKG_INSTROOT}" ] && exit 0
if ! sh /usr/libexec/mori-register; then
	echo 'Mori registration deferred. After resolving LuCI drafts, run sh /usr/libexec/mori-register.' >&2
fi
exit 0
endef

# Best-effort fallback only: apk does not abort removal when prerm fails.
# For a guarded uninstall, run the helper with --prepare-remove before apk del.
define Package/luci-theme-mori/prerm
#!/bin/sh
[ -n "$${IPKG_INSTROOT}" ] && exit 0
[ "$${PKG_UPGRADE}" = 1 ] && exit 0
if ! sh /usr/libexec/mori-register --prepare-remove; then
	echo 'Mori: removal was not prepared. APK may continue despite this failure; restore or select a working theme immediately.' >&2
	exit 1
fi
exit 0
endef

define Package/luci-theme-mori/postrm
#!/bin/sh
[ -n "$${IPKG_INSTROOT}" ] && exit 0
[ "$${PKG_UPGRADE}" = 1 ] && exit 0
# A stale inactive menu entry is safer than committing another user's draft.
if [ -z "$$(uci -q changes luci)" ] && [ "$$(uci -q get luci.themes.Mori)" = /luci-static/mori ]; then
	work=$$(mktemp -d /tmp/mori-unregister.XXXXXX) || exit 0
	trap 'rm -rf "$$work"' EXIT
	mkdir "$$work/config" "$$work/delta" || exit 0
	name=mori_unregister_$$$$
	[ ! -e "/tmp/.uci/$$name" ] || exit 0
	cp -p /etc/config/luci "$$work/luci.before" || exit 0
	cp "$$work/luci.before" "$$work/config/$$name" || exit 0
	uci -c "$$work/config" -t "$$work/delta" -q delete "$$name.themes.Mori" || exit 0
	uci -c "$$work/config" -t "$$work/delta" commit "$$name" || exit 0
	[ -z "$$(uci -q changes luci)" ] || exit 0
	cmp -s "$$work/luci.before" /etc/config/luci || exit 0
	cp -p /etc/config/luci "/etc/config/.luci-mori-next-$$$$" || exit 0
	cat "$$work/config/$$name" > "/etc/config/.luci-mori-next-$$$$" || exit 0
	mv "/etc/config/.luci-mori-next-$$$$" /etc/config/luci
fi
exit 0
endef

include $(TOPDIR)/feeds/luci/luci.mk

# call BuildPackage - OpenWrt buildroot signature
