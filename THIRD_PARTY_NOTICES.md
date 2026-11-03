# Third-party notices

Mori is distributed under the Apache License 2.0; see [LICENSE](LICENSE). Existing copyright and attribution notices in derived source files are retained.

## luci-theme-argon

- Upstream: [jerrykuku/luci-theme-argon](https://github.com/jerrykuku/luci-theme-argon)
- Reference release: [v2.4.3](https://github.com/jerrykuku/luci-theme-argon/tree/v2.4.3)
- Reference package: `2.4.3-r20250722`
- License: [Apache-2.0 at v2.4.3](https://github.com/jerrykuku/luci-theme-argon/blob/v2.4.3/LICENSE)

Mori's initial compatibility assets and ucode templates were derived from an installed Argon package at that version. Firmware packaging may contain downstream modifications; this does not claim that every imported file is an unmodified copy of the upstream tag.

The derived components are:

| Mori files | Source and changes |
| --- | --- |
| `ucode/template/themes/mori/*.ut` | Argon templates, modified for Mori branding, local assets, page scoping and appearance controls. Original template copyright headers are retained. |
| `htdocs/luci-static/mori/css/` | Argon compatibility styles; bundled display-font references are replaced with system fonts. Mori's own visual changes live in `mori.css`. |
| `htdocs/luci-static/resources/menu-mori.js` | Argon menu implementation, included under a Mori-specific module name. |
| `htdocs/luci-static/mori/fonts/argon.woff` and `argon.woff2` | Argon's icon font, retained to support the compatible menu and component icons. |
| `htdocs/luci-static/mori/icon/` and `img/` | Small compatibility assets from the same Argon package: arrows, a loading indicator, the blank background and volume-control icons. |

The retained icon-font files match the upstream v2.4.3 files:

```text
argon.woff   1f2d0d2837b0c22b440c6537a67f98f697d12c3ff490e99d64be26b3324fe1a3
argon.woff2  a2b317e0113b0e5eb3ffe4ec7559d784564f02e8624ba29bbc44d7afd74585a4
```

The source templates credit Jerrykuku / Jerryk and retain the following historical acknowledgements:

- `luci-theme-material`: Copyright 2015 Lutty Yang.
- `luci-theme-bootstrap`: Copyright 2008 Steven Barth; Copyright 2008–2016 Jo-Philipp Wich; Copyright 2012 David Menting.
- [MUI](https://github.com/muicss/mui) and [Creative Tim's Argon Dashboard](https://github.com/creativetimofficial/argon-dashboard).

Mori does not bundle the Google Sans or TypoGraphica display fonts, Argon's wallpaper, or Argon's branding images. The Mori logo and the theme-specific interface additions are part of Mori.

## LuCI runtime

Mori uses the installed [OpenWrt LuCI](https://github.com/openwrt/luci) runtime, native views, menu APIs and configuration flow. It does not redistribute a separate copy of the LuCI core. The original LuCI runtime and package licenses remain applicable to those installed components.

The independent Mori installer changes only theme files and LuCI theme options. Neither inclusion in this repository nor the Mori name implies endorsement by the upstream projects.
