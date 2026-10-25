https://github.com/user-attachments/assets/c827f059-cfd7-4f6a-bed3-8b00411a7220

> [!NOTE]
> **This is a community build** · 这是一个基于官方 PecoFence 的社区定制版
>
> 基于 [DayuanJiang/PecoFence](https://github.com/DayuanJiang/PecoFence) v0.2.3(含 main 分支未发布改动),在本仓库基础上做了以下增强:
>
> 1. **`selection.clearOnLeave`** — 鼠标离开围栏时自动清除图标选中,误点不再留下高亮(`pecofence-cli settings set selection.clearOnLeave true` 开启);
> 2. **卡死自愈** — watchdog 每 20 秒探测主程序,连续两次无响应即结束并自动重启,把"未响应崩溃"变成几秒钟的闪断(关机/注销不重启,快速崩溃循环不重复拉起);
> 3. **7 套新示例主题** — 墨玉、曜石、暮霞、宣纸、深海、青柠、纯白,加上原有 3 套共 10 套。
>
> 安装包与便携版在 [Releases](../../releases) 下载。上游的所有功能、CLI、文档保持不变;更新检查仍指向官方仓库。
> 遵循 Apache-2.0 许可证分发,上游版权与许可证文件完整保留。
>
> *A community build of [DayuanJiang/PecoFence](https://github.com/DayuanJiang/PecoFence) v0.2.3 with three additions: a `selection.clearOnLeave` setting (hover keeps the selection, leaving the fence clears it), a watchdog that detects a hung instance and restarts it, and seven more example themes. Installers are on the [Releases](../../releases) page. Everything else, including the CLI and docs, is unchanged from upstream; Apache-2.0, all rights and license files of the upstream project preserved.*

<p align="center">
  <strong>A free, open-source Stardock Fences alternative for Windows 11.</strong><br>
  Keep files in glass panels, switch projects with tabs, and ask your AI agent to configure the layout, appearance and sorting rules through the built-in CLI.
</p>

<p align="center">
  <a href="https://pecofence.jiang.jp/"><strong>Website</strong></a>
  &nbsp;·&nbsp; <a href="#get-pecofence"><strong>Get PecoFence →</strong></a>
  &nbsp;·&nbsp; <a href="#your-desktop-configured-by-your-ai"><strong>AI + CLI</strong></a>
  &nbsp;·&nbsp; <a href="#see-it-in-action">See it in action</a>
  &nbsp;·&nbsp; <a href="docs/README.md">Documentation</a>
</p>

<p align="center">
  <strong>English</strong>
  &nbsp;·&nbsp; <a href="docs/readme/README.zh-CN.md">简体中文</a>
  &nbsp;·&nbsp; <a href="docs/readme/README.zh-TW.md">繁體中文</a>
  &nbsp;·&nbsp; <a href="docs/readme/README.ja.md">日本語</a>
  &nbsp;·&nbsp; <a href="docs/readme/README.ko.md">한국어</a>
  &nbsp;·&nbsp; <a href="docs/readme/README.de.md">Deutsch</a>
  &nbsp;·&nbsp; <a href="docs/readme/README.fr.md">Français</a>
  &nbsp;·&nbsp; <a href="docs/readme/README.es.md">Español</a>
  &nbsp;·&nbsp; <a href="docs/readme/README.pt-BR.md">Português (Brasil)</a>
  &nbsp;·&nbsp; <a href="docs/readme/README.ru.md">Русский</a>
</p>

---

<a id="ask-your-ai-to-organize-it"></a>

## Your desktop. Configured by your AI

**Built-in CLI. Ready for your AI agent.**

Tell your AI agent how you want your desktop to work. The bundled `pecofence-cli` lets Claude Code, Codex and Cursor read your current setup and apply changes directly in PecoFence.

- **Configure it in your own words.** Change themes, transparency, icon sizes and global settings, or adjust every fence at once.
- **Organize once. Keep it organized.** Create project fences, arrange icons and add rules that sort new files automatically.
- **Save a setup you like.** Use snapshots for fence layouts and configuration export/import for settings, rules and layouts.

**Try it with your AI agent**

Open PecoFence, then paste this request into your AI coding agent:

> Use pecofence-cli to configure my desktop. First read pecofence-cli skill and pecofence-cli describe, then inspect my current settings and fences. Back up my configuration before changes. Switch to dark mode and make all fences more transparent.

The CLI is included. The Microsoft Store edition adds `pecofence-cli` to PATH. With the portable ZIP, give your agent the path to `pecofence-cli.exe`.

<details>
<summary><strong>Example conversation with a coding agent</strong></summary>

> Put my desktop PDFs in a Docs fence, keep new PDFs there, switch to dark mode and make the fences more transparent.

```powershell
pecofence-cli config export "$env:USERPROFILE\pecofence-before-ai.json"
pecofence-cli snapshot save before-cleanup
pecofence-cli fence create --title Docs
pecofence-cli rule add --name PDFs --ext pdf --to Docs --index 0
pecofence-cli rule apply
pecofence-cli settings set theme dark
pecofence-cli fence set --all opacity clear
```

</details>

Built for agents and scripts: `describe` exposes the command catalog and JSON Schemas; `skill` prints the agent guide. JSON results report what changed, and structured application errors help the agent choose its next step.

[Get started with the CLI →](docs/CLI.md#start-with-your-ai-agent)

## Give everything a place

<p align="center">
  <img src="docs/assets/hero-en.png" alt="PecoFence — Project folders, a PDF and original design studies in Liquid Glass fences." width="1280">
</p>

## See it in action

### One fence. Multiple workspaces.

Keep related fences together as tabs. Switch from Project to Ideas in a click,
then drag a tab out when you want the extra room.

![Merging two fences into tabs, switching between Project and Ideas, then dragging a tab out into its own fence.](docs/assets/tabs.gif)

### Your desktop, one shortcut away.

Press **Ctrl + Alt + Space** to bring your fences above the current application.
Grab what you need, then press **Esc** to return.

![Peek brings your fences above an application; a click outside or opening a file returns to it.](docs/assets/peek.gif)

<sub>Animations from the <a href="https://pecofence.jiang.jp/manual/">user manual</a>. GIFs loop automatically.</sub>

## Small details that add up

| Feature | What you get |
| :--- | :--- |
| **AI + CLI** | `pecofence-cli` — **Configure it in your own words.** Change themes, transparency, icon sizes and global settings, or adjust every fence at once. |
| **Less sorting** | Rules for file types, extensions, names, wildcards, shortcut targets, time and size. New files find their fence automatically. |
| **Glass that fits your desktop** | Fluent and Liquid Glass themes, light/dark modes, per-fence colors, opacity and icon tinting. |
| **Familiar file handling** | File Explorer context menus, drag and drop, copy/paste, multi-select, thumbnails and icon/list/details views. |
| **Keep folders close** | Put a live folder on your desktop. Browse subfolders and see changes as they happen. |
| **Space when you need it** | Roll a fence up to its title. Hover to expand. Lock a layout you like. Double-click the desktop to hide your fences. Double-click again to bring them back. |
| **A way back** | Layout snapshots, daily backups, configuration import/export and swapping fences between displays. |
| **A small footprint** | A native Rust application that idles at about 40 MB of memory in Task Manager. The WebView2 settings panel loads on demand. |

Automatic sorting rules keep files in their original locations. File moves you
initiate work like they do in File Explorer.

[Explore the complete feature list →](docs/FEATURES.md)

## Get PecoFence

<a href="https://apps.microsoft.com/detail/9MV6WG3XNWSX?mode=direct"><img src="https://get.microsoft.com/images/en-us%20dark.svg" alt="Get it from Microsoft Store" width="200"></a>

The Microsoft Store edition is signed by Microsoft, updates automatically and never shows a SmartScreen prompt. The same app also comes as:

- **Portable ZIP**: download `pecofence-v<version>-x64-portable.zip` from this repository's **Releases** page, extract the **whole ZIP** into a folder and run `pecofence.exe`.
- **Installer**: `pecofence-v<version>-x64-setup.exe` on the same page installs PecoFence for your Windows user, with a Start menu entry and an uninstaller.
- **winget**: `winget install DayuanJiang.PecoFence` installs the portable build and skips the SmartScreen prompt.

<details>
<summary><strong>Requirements, configuration and a few useful notes</strong></summary>

- Windows 10 22H2, or Windows 11 22H2 or later. Settings needs the Microsoft Edge WebView2 Runtime. Windows 11 includes it; on Windows 10 install it from Microsoft if Settings does not open.
- The first launch creates four fences in your selected language: Programs, Folders, Files and documents, and Desktop. Windows desktop icons are restored when you exit.
- Configuration lives in `%APPDATA%\PecoFence\config.json`. Launch with `--portable` to keep it in a `config` folder beside the executable.
- The ZIP and the installer are unsigned. If Windows SmartScreen appears on first launch, choose **More info → Run anyway**.

[Portable edition guide](docs/PORTABLE.md) · [Language guide](docs/LOCALIZATION.md) · [Windows installer guide](docs/INSTALLER.md)

</details>

## Build it. Make it yours.

PecoFence is Apache 2.0 licensed, and contributions are welcome—from a sharper translation
to a better desktop interaction.

[Contribute](CONTRIBUTING.md) · [Improve a translation](docs/LOCALIZATION.md) · [Development guide](docs/DEVELOPMENT.md)

---

**Made for a desktop you enjoy coming back to.**  
[Apache License 2.0](LICENSE) · [Third-party notices](third_party/README.md)

Thanks to the [LINUX DO](https://linux.do) community.
