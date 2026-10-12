# lwe-gui-slint

Linux Wallpaper Engine 壁纸管理器，用 Python + [Slint](https://slint.dev) 写。
窗口里只有一个壁纸列表和一条底部信息栏：选中、调帧率、应用 / 停止。

## 功能

- 扫描 `~/.local/share/Steam/steamapps/workshop/content/431960`，读取 `project.json` 的标题与类型
- 列表展示缩略图（作者封面图优先）、标题、创意工坊 id，点击选中
- 底部信息栏：选中标题 / 元信息 / 状态，帧率读数与滑杆（1–120），应用 / 停止
- 应用时自动关闭作者在工程里提供的「提示框」浮层
- 引擎启动后确认存活，失败时把引擎 stderr 的原因显示到状态栏

## 代码结构

按职责分文件，每个模块只做一件事：

```
src/lwe_gui_slint/
├── config.py      路径与常量集中一处；环境变量开关也只在这里读一次
├── model.py       扫描创意工坊目录（纯函数 + dataclass）
├── preview.py     缩略图：把视频/动图抽一帧静态图并缓存
├── session.py     Hyprland / Wayland 环境与显示器探测
├── settings.py    作者在工程里暴露的开关（目前只有「提示框」）
├── engine.py      引擎进程控制与状态机
├── main.py        UI 绑定与编排
└── __main__.py    支持 python -m lwe_gui_slint
```

几条约定：

- **只在一处拼路径**：所有缓存与日志路径都在 `config.py`
- **状态机只有一处**：`WallpaperEngine.apply()` 只有 `_spawn_and_verify()` 一条收尾路径，
  不会出现「进程秒退却报已加载」
- **缩略图在工作线程抽帧，图片解码必须在主线程**：`slint.Image` 被 pyo3 标记为
  unsendable，跨线程传递会直接 abort 进程

## 预览

**没有大预览面板**。窗口里只有列表，缩略图是 72×40。

Slint 不自带 GIF 与视频解码（遇到 GIF 直接报 `The image format Gif is not supported`），
所以缩略图用 ffmpeg 抽第一帧；素材本身是 PNG/JPEG 的直接用原文件。
缩略图优先用作者封面图（`preview.jpg/png`），它比视频首帧亮、更有代表性。

早期版本做过大预览面板 + 引擎离屏渲染高清图（`--screenshot`），已整体移除：
那个机制要起第二个引擎实例，对个别场景会拿到黑帧、对视频壁纸会拿到 mpv/vaapi
花屏帧，是各类问题的根源。

## 界面设计

排版驱动层级，不用卡片与玻璃效果：

- 近黑画布（`#0b0b0c`）+ 单一强调色琥珀（`#d8a657`），没有第二种彩色
- 圆角只用 2px，分隔靠 1px 细线；没有渐变条、没有状态圆点、没有居中占位大字
- 数字与标签用等宽字体 Maple Mono 并拉开字距，正文用 Noto Sans CJK SC
- 选中行只在左侧亮起 2px 琥珀竖线，未选中行的缩略图压到 45% 不透明度
- 所有设计令牌集中在 `ui/theme.slint`

## 窗口尺寸

给的是 `preferred-width/height`（760×620）与 `min-width/height`（420×320），
**没有**用 `width` / `height`——后者会把窗口锁成固定尺寸（min = max），
窗口管理器无法平铺或缩放。

平铺窗口管理器会自己决定尺寸，这几个值只在浮动式 WM 下作为初值。
最小尺寸特意留得小，方便平铺时压窄。

## 运行环境要点

引擎对会话环境很敏感，程序会自己补齐，不依赖启动它的终端：

- `HYPRLAND_INSTANCE_SIGNATURE` 没设时，从 `$XDG_RUNTIME_DIR/hypr/*/.socket.sock` 推断，
  否则 `hyprctl` 只会打印错误文本，显示器名会被解析成字符串 `not`
- `WAYLAND_DISPLAY` 没设时，从 `$XDG_RUNTIME_DIR/wayland-*` 推断；
  `XDG_SESSION_TYPE` 必须与之一致，判错会报 `Failed to detect any supported platform` 直接退出
- 启动后等 2 秒确认进程存活，5 秒再复检一次

## 作者提示框

部分壁纸（实测 5 张，多为「夜莺 Night」的作品）带一个「壁纸作者有话说」浮层，
作者在壁纸里写明「此提示框可在用户设置永久关闭」。这个开关是 `project.json`
里的一个 bool 属性，但它**没有 `user` 标记**，只能按标签识别：

```python
NOTICE_PATTERN = re.compile(r"提示框|prompt\s*box|notice", re.IGNORECASE)
```

键名逐张不同（实测有 `fontcolorff4848bigbpromptbox`、`bigb`，
还有一张键名是乱的 `brbbrbreathinganimation` 但标签写的是「🔘提示框 Prompt Box」），
所以必须按标签匹配。命中的属性以 `--set-property <key>=0` 传给引擎。

想保留作者原样：`LWE_KEEP_NOTICE=1`。

## 依赖

- uv：管理 Python 3.13 解释器与虚拟环境
- ffmpeg / ffprobe：抽缩略图，必需
- linux-wallpaperengine、hyprctl：应用壁纸
- NixOS 侧：nix-ld 需提供 wayland / xorg / freetype / fontconfig / libGL（当前配置已覆盖）

## Nix 安装

本包是本仓库（nix-flakes）里的一个包，源码即 `packages/lwe-gui-slint`：

```bash
nix build github:ryan43705431/nix-flakes#lwe-gui-slint
./result/bin/lwe-gui-slint
```

包内 wrapper 把 `ffmpeg`、`linux-wallpaperengine`、`procps` 放进 PATH，`ui/` 随包安装到
`$out/share/lwe-gui-slint/ui` 并由 `LWE_UI_DIR` 指向，所以不依赖当前工作目录，也不依赖
从哪个终端启动。装进 NixOS 配置的方式见仓库根 README。

## 运行

```bash
cd ~/myfiles/nix-flakes/packages/lwe-gui-slint
uv run lwe-gui-slint
```

调试日志：

```bash
LWE_DEBUG=1 uv run lwe-gui-slint
```

## 缓存

全部在 `~/.cache/lwe-gui-slint/`，可随时删除。
缓存键里有 `CACHE_VERSION`（`config.py`），改动抽帧策略时递增即可让旧缓存自动失效：

| 路径 | 内容 |
| --- | --- |
| `previews/` | 缩略图 PNG，文件名含源文件 mtime |
| `engine.log` | 引擎最后一次运行的 stderr，排查「应用没反应」看这里 |
| `wallpaper.pid` | 当前壁纸进程 pid |

## 已知限制

- slint 目前只有预发布版本（1.18.1b1），API 可能变动
- `ui/*.slint` 在 Python 包目录之外：从源码运行时必须在项目根目录启动（打进 wheel 会找不到），
  nix 安装由 `LWE_UI_DIR` 指向 `$out/share/lwe-gui-slint/ui`
- 缩略图受素材限制：创意工坊里不少壁纸的 `preview.gif` 只有 160–256px，
  在 72×40 的尺寸下够用，但放不大
- 暂停 / 恢复播放没有实现，要停就点「停止」
