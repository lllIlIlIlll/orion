# `frontends/` 目录结构重构设计

- **日期**: 2026-07-10
- **状态**: 已确认，待编写实施计划
- **范围**: 仅重组 `frontends/` 目录结构与同步更新引用，不改业务逻辑

## 1. 背景与动机

`frontends/` 目前是 **34 个 `.py` 文件平铺一层**，外加几个子目录（`skins/`、`desktop/`、`conductor_im_plugins/`），混入了 5 类完全不同的关注点：

| 类别 | 文件 |
|---|---|
| IM 机器人前端（都依赖 `chatapp_common`） | `qqapp` `dcapp` `tgapp` `dingtalkapp` `wechatapp` `wecomapp` `fsapp` |
| 终端 TUI（三代并存） | `tuiapp`（v1）`tuiapp_v2`（v2）`tui_v3`（v3，README 推荐） |
| Web / Streamlit（两代并存） | `stapp` `stapp2` |
| 桌面端 | `qtapp`（PySide6）`desktop/`（Tauri）`desktop_pet_v2.pyw` `desktop_bridge.py` |
| 编排 / 桥接 | `conductor.py`+`conductor.html`+`conductor_im_plugins/` `tau_acp_bridge.py` |
| 共享 UI 无关逻辑（14 个） | `chatapp_common` `slash_cmds` `continue_cmd` `btw_cmd` `review_cmd` `export_cmd` `model_cmd` `workspace_cmd` `at_complete` `worldline` `plan_state` `cost_tracker` `session_names` `keysym` |
| 资产 | `skins/` `chat_bubble.png` `DESKTOP_PET_README.md` |

明显的"乱"点：① 无层级，应用与共享库平铺；② 多代版本并存且命名不统一（`tuiapp_v2` vs `tui_v3`）；③ 外部有大量硬编码 `frontends/xxx.py` 路径，动结构需同步改。

## 2. 目标与非目标

### 目标
- 把平铺文件按**运行载体**归类到子目录，消除"一层乱"。
- 把跨子目录依赖转成清晰的绝对包 import，依赖关系一目了然。
- 同步更新所有外部引用，保证重构后功能与重构前完全等价。

### 非目标（明确排除）
- **不删任何文件**：包括 `tuiapp.py` v1、`stapp.py` v1 等旧版本，全部保留。
- **不动业务逻辑**：不改函数/类/变量名、不改文件内控制流。唯一允许的文件内改动是 **import 行、`sys.path`/`ROOT` setup 行**，以及第 5 节列出的"自动发现"扫描逻辑。
- **不做深度整理**：不统一版本命名（`tuiapp_v2`→`tui_v2` 之类）、不拆超大文件、不合并重复实现、不抽公共子包 API。

## 3. 目标目录树

```
frontends/
├── __init__.py                 # 新增，使 frontends 成为包
├── bots/                       # IM 机器人前端
│   ├── __init__.py
│   ├── qqapp.py  dcapp.py  tgapp.py  dingtalkapp.py
│   ├── wechatapp.py  wecomapp.py  fsapp.py
├── tui/                        # 终端 UI（三代并存，全部保留）
│   ├── __init__.py
│   └── tuiapp.py  tuiapp_v2.py  tui_v3.py
├── web/                        # Streamlit Web 前端
│   ├── __init__.py
│   └── stapp.py  stapp2.py
├── desktop/                    # 桌面端（沿用现有 desktop/ 目录）
│   ├── __init__.py
│   ├── qtapp.py                # 顶层移入
│   ├── desktop_pet_v2.pyw      # 顶层移入
│   ├── desktop_bridge.py       # 顶层移入
│   ├── chat_bubble.png         # 顶层移入（仅 pet 用）
│   ├── DESKTOP_PET_README.md   # 顶层移入
│   ├── skins/                  # 顶层移入（仅 pet 用）
│   ├── src-tauri/              # ← 原样不动
│   ├── static/                 # ← 原样不动
│   └── package.json            # ← 原样不动
├── conductor/                  # 多 subagent 编排
│   ├── __init__.py
│   ├── conductor.py  conductor.html
│   └── conductor_im_plugins/
├── acp/                        # ACP JSON-RPC 桥接
│   ├── __init__.py
│   └── tau_acp_bridge.py
└── shared/                     # 14 个 UI 无关共享模块
    ├── __init__.py
    ├── chatapp_common.py       # bots + tui/qtapp 共用，故放 shared
    ├── slash_cmds.py  continue_cmd.py  btw_cmd.py  review_cmd.py
    ├── export_cmd.py  model_cmd.py  workspace_cmd.py  at_complete.py
    ├── worldline.py  plan_state.py  cost_tracker.py
    └── session_names.py  keysym.py
```

### 关键决策

1. **`desktop/` 冲突**：沿用现有 `desktop/` 目录作为载体，把 `qtapp`/`desktop_pet_v2`/`desktop_bridge`/资产作为兄弟加入；**Tauri 的 `src-tauri/`、`static/`、`package.json` 原地不动**。理由：`src-tauri/tauri.conf.json` 用相对路径 `../static`，且 `static/assets/fonts/README.md` 外部文档引用 `frontends/desktop/static/...`，改变嵌套层级有风险。
2. **`chatapp_common` 放 `shared/` 而非 `bots/`**：除 7 个 bot 外，`tui/qtapp.py` 与 `tuiapp_v2.py` 也 import 它。放 `shared/` 避免出现"tui 反向依赖 bots"。
3. **不设顶层 `assets/`**：现有 3 项资产（`skins/`、`chat_bubble.png`、`DESKTOP_PET_README.md`）均只被 `desktop_pet_v2.pyw` 引用，直接归入 `desktop/`，无需多设一层空架子。

## 4. import 改造规则

**统一规则**：所有**跨子目录**的 import 改成绝对包式 `from frontends.<子目录>.<模块> import ...`。同子目录内的 import 也统一改成绝对式以保持一致。**只动 import 行与 `sys.path`/`ROOT` setup 行，不碰业务逻辑。**

### 4.1 import 行映射

| 文件（新位置） | 现在 | 改成 |
|---|---|---|
| `bots/*.py` | `from chatapp_common import …` | `from frontends.shared.chatapp_common import …` |
| `bots/*.py` | `from continue_cmd / btw_cmd / review_cmd import …` | `from frontends.shared.<cmd> import …` |
| `bots/fsapp.py` | `from frontends.chatapp_common import …` | `from frontends.shared.chatapp_common import …` |
| `tui/qtapp.py` | `from chatapp_common import …` | `from frontends.shared.chatapp_common import …` |
| `tui/tuiapp_v2.py` | `from keysym / at_complete / btw_cmd / review_cmd / continue_cmd / worldline import …`；`import chatapp_common`；`import workspace_cmd`；`from frontends.slash_cmds import …` | 全部加 `frontends.shared.` 前缀 |
| `tui/tui_v3.py` | `from frontends import at_complete, workspace_cmd` | `from frontends.shared import at_complete, workspace_cmd` |
| `tui/tuiapp.py`、`web/stapp*.py` | 各自的 `chatapp_common` / `continue_cmd` / `btw_cmd` / `export_cmd` | 加 `frontends.shared.` 前缀 |
| `shared/chatapp_common.py` | `from continue_cmd / btw_cmd / review_cmd import …` | `from frontends.shared.<cmd> import …` |
| `shared/export_cmd.py` | `from continue_cmd import …` | `from frontends.shared.continue_cmd import …` |

> 实施时需对每个被移动文件全量扫描 `^import` / `^from`，按规则改写；上表仅列已知的跨目录依赖，遗漏的同类依赖同样按规则处理。

### 4.2 连带 setup 行改动

1. **`ROOT` / `sys.path` 深度 +1**：各 app 现在用 `os.path.dirname(os.path.dirname(os.path.abspath(__file__)))` 算项目根（因当前位于 `frontends/<file>`，两层 `dirname` 到根）。搬深一层后需改为三层 `dirname`。这是让 `from agentmain import Tau` 与 `import frontends` 继续工作的必要调整。涉及：`bots/*`、`tui/*`、`web/*`、`desktop/qtapp.py`、`desktop/desktop_bridge.py`、`conductor/conductor.py`、`acp/tau_acp_bridge.py`。
2. **`__init__.py` 全部留空**：`frontends/` 本身 + 7 个子目录（`bots` `tui` `web` `desktop` `conductor` `acp` `shared`）各加一个空 `__init__.py`，纯粹为成为包，**不主动导出任何符号**（避免隐式耦合）。`conductor_im_plugins/` 当前无 `__init__.py`（仅含 `_TEMPLATE.py` / `_email_example.py` / `_lark_example.py`），实施时按 `conductor/conductor.py` 对它的实际 import 方式决定是否补 `__init__.py`，不主动改其内部结构。

### 4.3 不改的边界
- 函数/类/变量名、文件内控制流、各 app 的运行方式（仍以 `python frontends/bots/tgapp.py` 直接运行）。

## 5. 外部引用更新清单

### 5.1 A 类 · 纯路径字符串替换（零逻辑改动）

| 文件 | 改动 |
|---|---|
| `tau_cli/cli.py` | `qtapp.py`→`desktop/qtapp.py`；`tuiapp.py`→`tui/tuiapp.py`；`tuiapp_v2.py`→`tui/tuiapp_v2.py` |
| `launch.pyw` | `frontends/stapp.py`→`frontends/web/stapp.py` |
| `README.md` | 所有 `frontends/<app>.py` 补上对应子目录 |
| `memory/review_sop.md` | `frontends/review_cmd.py`→`frontends/shared/review_cmd.py` |
| `desktop/desktop_bridge.py` | `_SERVICE_KEYS` 的 6 个 key、`discover_extra_services` 的 conductor 路径、docstring 示例，分别补 `bots/`、`conductor/` |
| `shared/slash_cmds.py` | help 文本与启动逻辑中的 `"frontends/conductor.py"`、picker 的 `rel` 拼接补子目录 |

### 5.2 B 类 · "自动发现"扫描逻辑的最小改动（唯一越界点）

现状有 **4 处**扫描 `frontends/` **扁平**目录来自动发现可启动 app，文件搬进子目录后将扫不到，必须改为扫描各载体子目录：

1. `hub.pyw` `discover_services()` — `os.listdir(frontends)`，并对 `stapp` 特判走 streamlit（`stapp` 现位于 `web/`）。
2. `shared/slash_cmds.py` `list_launchable_services()` — 镜像 `hub.pyw`。
3. `desktop/desktop_bridge.py` `discover_im_services()` / `discover_extra_services()`。
4. `shared/at_complete.py` 的 `@` 补全文件索引（`@frontends/x.py` 重写逻辑）。

**改动原则**：只让发现逻辑学会进入各载体子目录扫描（`frontends/{bots,tui,web,desktop,conductor,acp}/*.py`），**不合并这 4 份重复实现、不重构它们**（合并属于已排除的深度整理）。

> 说明：`_SKIP` / `EXCLUDES` 集合（如 `chatapp_common.py`、`tuiapp.py`、`qtapp.py` 等）需复核——部分被排除项已迁入 `shared/` 或 `desktop/`，发现范围本身的变化可能已使部分排除规则失效；实施时以"重构前后发现到的服务集合完全一致"为验收标准。

## 6. 验收标准

1. 重构后每个原入口都能正常启动：`tau tui` / `tau tui2` / `tau gui`(qtapp) / 各 bot / `python frontends/tui/tui_v3.py` / `python frontends/conductor/conductor.py` / `launch.pyw`。
2. **自动发现的服务集合与重构前完全一致**（`hub.pyw`、`slash_cmds.list_launchable_services()`、`desktop_bridge.discover_im_services()`）。
3. `@` 补全仍能找到并正确重写 `frontends/<载体>/<file>.py` 形式的提及。
4. 无新增 `import` 报错：所有被移动文件可直接 `python` 运行且能 import `agentmain` 与 `frontends.*`。
5. `frontends/desktop/` 下 Tauri 项目（`src-tauri/`、`static/`、`package.json`）相对路径未变，构建不受影响。

## 7. 风险与缓解

- **风险**：漏改某处外部引用 → 运行时才暴露。**缓解**：实施计划中以"依赖关系全量扫描"为独立步骤，对 `frontends/` 每个被移动文件 grep 其旧路径，逐个核对。
- **风险**：`__init__.py` 使 `frontends` 成为包后，个别脚本以非预期方式操作 `sys.path` 可能冲突。**缓解**：保留各 app 现有的"插入项目根到 `sys.path`"做法，仅调整 `dirname` 深度。
- **风险**：4 处发现逻辑改动后行为漂移（多扫/少扫）。**缓解**：以验收标准 #2 为准，重构前后导出服务清单做 diff。

## 8. 后续

本设计确认后，转入 `writing-plans` 制定逐步实施计划。实施应按"先搬共享层 → 改 import → 搬应用层 → 改外部引用 → 验收"顺序，保证每一步仓库可运行。
