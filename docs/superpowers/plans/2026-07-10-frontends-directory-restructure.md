# frontends/ 目录结构重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `frontends/` 下 34 个平铺文件按运行载体归类到 7 个子目录，转成绝对包 import，同步更新所有外部引用，行为与重构前完全等价。

**Architecture:** 纯搬家重构。先建包骨架并捕获发现逻辑基线 → 搬 `shared/` 并改写全仓所有 shared 模块 import → 逐载体搬移并修各文件 `__file__` 路径 → 重写 4 处自动发现逻辑使其扫描子目录 → 更新外部启动器与文档字符串。每个 task 结束仓库可编译、可 import。

**Tech Stack:** Python 3，标准库 `os`/`sys`/`pathlib`；无新依赖。

## Global Constraints

摘自 spec `docs/superpowers/specs/2026-07-10-frontends-directory-restructure-design.md`：

- **不删任何文件**：含 `tuiapp.py`(v1)、`stapp.py`(v1) 等旧版本，全部保留。
- **不改业务逻辑**：唯一允许的文件内改动是 (a) import 行、(b) `sys.path`/`ROOT`/`__file__` 路径 setup 行、(c) 第 9 个 task 中 4 处"自动发现"扫描逻辑。函数/类/变量名、控制流一律不动。
- **7 个子目录**：`bots` `tui` `web` `desktop` `conductor` `acp` `shared`，各加空 `__init__.py`；`frontends/__init__.py` 亦新增。`__init__.py` 不导出任何符号。
- **import 统一为绝对包式**：`from frontends.<子目录>.<模块> import ...`。
- **`desktop/` 沿用现有目录**：Tauri 的 `src-tauri/`、`static/`、`package.json` 原地不动（`tauri.conf.json` 用 `../static` 相对路径）。
- **`chatapp_common` 放 `shared/`**（bots + tui/qtapp 共用）。
- **跨载体 import 不存在**：应用文件只 import `shared`，不互相 import（已验证）。这是载体可独立搬移的前提。
- **shared 14 模块集合**：`chatapp_common slash_cmds continue_cmd btw_cmd review_cmd export_cmd model_cmd workspace_cmd at_complete worldline plan_state cost_tracker session_names keysym`。
- **GREEN 定义**（每个 task 末尾必须满足）：所有被移动/修改的 `.py` 通过 `python -m py_compile`；`shared` 模块可被 `python -c "import frontends.shared.<m>"` 导入；`grep` 审计无残留旧式 flat import 或旧路径字符串（task 9/10 专门处理的除外）。自动发现集合的精确对齐在 task 9 验收。

> **测试方法说明**：本计划是机械重构，无新功能，因此不采用"先写失败单测"的 TDD 循环。验证手段是：编译检查、import 冒烟、`grep` 审计、以及 task 1 捕获/task 9 比对的"发现集合前后一致"。

---

## File Structure（最终归属，锁定分解决策）

```
frontends/
├── __init.py__ (Task 1)
├── bots/      __init__.py (T1); qqapp dcapp tgapp dingtalkapp wechatapp wecomapp fsapp (T3)
├── tui/       __init__.py (T1); tuiapp tuiapp_v2 tui_v3 (T4)
├── web/       __init__.py (T1); stapp stapp2 (T5)
├── desktop/   __init__.py (T1); qtapp desktop_pet_v2.pyw desktop_bridge chat_bubble.png DESKTOP_PET_README.md skins/ (T6); [src-tauri static package.json 不动]
├── conductor/ __init__.py (T1); conductor.py conductor.html conductor_im_plugins/ (T7)
├── acp/       __init__.py (T1); tau_acp_bridge.py (T8)
└── shared/    __init__.py (T1); 14 模块 (T2)
```

外部需改文件：`hub.pyw`、`tau_cli/cli.py`、`launch.pyw`、`README.md`、`memory/review_sop.md`（Task 9/10）。

---

### Task 1: 建立包骨架 + 捕获发现逻辑基线

**Files:**
- Create: `frontends/__init__.py`, `frontends/bots/__init__.py`, `frontends/tui/__init__.py`, `frontends/web/__init__.py`, `frontends/conductor/__init__.py`, `frontends/acp/__init__.py`, `frontends/shared/__init__.py`（均空文件）
- Create: `frontends/desktop/__init__.py`（`desktop/` 已存在，仅补 `__init__.py`）
- Create: `/tmp/tau_discovery_baseline.json`（基线快照，不进 git）

**Interfaces:** 无（本 task 不产生被他人依赖的符号，仅建立目录与基线）。

- [ ] **Step 1: 捕获自动发现基线（在改动前）**

  先确认 `hub.pyw` 的 GUI 启动是否在 `__main__` 守卫下（决定能否安全 import）：

  ```bash
  sed -n '270,280p' hub.pyw
  ```

  预期看到 `app = LauncherApp(root)`。若该行在 `if __name__ == '__main__':` 之下，则 import 安全；否则跳过 hub 的基线捕获（仅捕获另外两个），并在 task 9 手工核对。

  捕获基线（在仓库根执行；三个发现函数的输出合并存档）：

  ```bash
  python - <<'PY' > /tmp/tau_discovery_baseline.json
  import sys, json
  sys.path.insert(0, ".")
  out = {}
  # slash_cmds
  try:
      from frontends.slash_cmds import list_launchable_services
      out["slash_cmds"] = list_launchable_services()
  except Exception as e:
      out["slash_cmds"] = f"ERR: {e}"
  # desktop_bridge
  try:
      from frontends.desktop_bridge import discover_im_services, discover_extra_services
      from pathlib import Path
      root = Path(".")
      out["desktop_bridge_im"] = discover_im_services(root)
      out["desktop_bridge_extra"] = discover_extra_services(root)
  except Exception as e:
      out["desktop_bridge"] = f"ERR: {e}"
  # hub (only if __main__-guarded)
  import ast
  src = open("hub.pyw").read()
  guarded = "if __name__" in src
  if guarded:
      try:
          import importlib.util
          spec = importlib.util.spec_from_file_location("hub_baseline", "hub.pyw")
          hub = importlib.util.module_from_spec(spec); spec.loader.exec_module(hub)
          out["hub"] = hub.discover_services()
      except Exception as e:
          out["hub"] = f"ERR: {e}"
  else:
      out["hub"] = "SKIPPED(not __main__-guarded; reconcile manually in Task 9)"
  print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
  PY
  cat /tmp/tau_discovery_baseline.json
  ```

  记录输出。这是 task 9 的对照基准。

- [ ] **Step 2: 建立空 `__init__.py` 包骨架**

  ```bash
  : > frontends/__init__.py
  mkdir -p frontends/bots frontends/tui frontends/web frontends/conductor frontends/acp frontends/shared
  : > frontends/bots/__init__.py
  : > frontends/tui/__init__.py
  : > frontends/web/__init__.py
  : > frontends/conductor/__init__.py
  : > frontends/acp/__init__.py
  : > frontends/shared/__init__.py
  : > frontends/desktop/__init__.py
  ```

  注意：`desktop/`、`conductor_im_plugins/` 已存在不重建；`conductor_im_plugins/` 是否补 `__init__.py` 留待 Task 7 按 `conductor.py` 对它的 import 方式决定。

- [ ] **Step 3: 验证未破坏现状（GREEN）**

  加空 `__init__.py` 不应影响现有 flat import（`frontends/` 仍在 `sys.path` 上）。冒烟验证：

  ```bash
  python -m py_compile frontends/*.py
  python -c "import sys; sys.path.insert(0,'frontends'); import chatapp_common; print('flat import ok')"
  python -c "import frontends.chatapp_common; print('abs import ok')"
  ```

  预期：三条均无异常（"flat import ok"、"abs import ok"）。

- [ ] **Step 4: Commit**

  ```bash
  git add frontends/__init__.py frontends/bots frontends/tui frontends/web frontends/conductor frontends/acp frontends/shared frontends/desktop/__init__.py
  git commit -m "refactor(frontends): scaffold package layout (empty __init__.py)"
  ```

---

### Task 2: 搬迁 shared/ + 全仓改写 shared 模块 import + 修 shared 文件 __file__ 路径

**Files:**
- Move (via `git mv`): 14 个 shared 模块从 `frontends/` → `frontends/shared/`：
  `chatapp_common.py slash_cmds.py continue_cmd.py btw_cmd.py review_cmd.py export_cmd.py model_cmd.py workspace_cmd.py at_complete.py worldline.py plan_state.py cost_tracker.py session_names.py keysym.py`
- Modify（import 改写）：下列文件中对 shared 模块的 import 行（具体由 Step 2 的 grep 枚举）
  - shared 内部：`chatapp_common.py`、`export_cmd.py`
  - apps（仍在顶层）：`dcapp.py dingtalkapp.py fsapp.py qqapp.py qtapp.py stapp.py tgapp.py wecomapp.py tuiapp_v2.py tui_v3.py`（已知）；`stapp2.py tuiapp.py wechatapp.py`（需 grep 复核）
- Modify（`__file__` 路径）：`chatapp_common.py export_cmd.py continue_cmd.py session_names.py review_cmd.py workspace_cmd.py slash_cmds.py`（凡含项目根/`temp` 路径计算的 shared 文件）

**Interfaces:**
- Produces：`frontends.shared.*` 这 14 个模块成为全仓唯一的 shared 入口；后续 task 的载体文件依赖这些绝对路径。

- [ ] **Step 1: 用 git mv 搬迁 14 个 shared 模块**

  ```bash
  cd frontends
  for m in chatapp_common slash_cmds continue_cmd btw_cmd review_cmd export_cmd model_cmd workspace_cmd at_complete worldline plan_state cost_tracker session_names keysym; do
      git mv "$m.py" "shared/$m.py"
  done
  cd ..
  ```

- [ ] **Step 2: 枚举全仓所有 shared 模块 import（权威清单）**

  在仓库根执行，记录全部命中行（含函数内缩进的惰性 import）：

  ```bash
  echo "=== Rule A/B: flat sibling imports ==="
  grep -rnE "(^|[[:space:]])(import|from)[[:space:]]+(chatapp_common|slash_cmds|continue_cmd|btw_cmd|review_cmd|export_cmd|model_cmd|workspace_cmd|at_complete|worldline|plan_state|cost_tracker|session_names|keysym)\b" frontends/ tau_cli/ *.py *.pyw 2>/dev/null
  echo "=== Rule C/D: frontends-prefixed imports still pointing at flat modules ==="
  grep -rnE "from frontends\b" frontends/ tau_cli/ *.py *.pyw 2>/dev/null | grep -vE "frontends\.(shared|bots|tui|web|desktop|conductor|acp)\b"
  ```

  预期命中（已知，用于校对，实际以 grep 输出为准）：
  - `shared/chatapp_common.py`：`from continue_cmd/btw_cmd/review_cmd import ...`
  - `shared/export_cmd.py`：`from continue_cmd import _pairs, _assistant_text`
  - `dcapp.py:11`、`dingtalkapp.py:6`、`qqapp.py:6`、`qtapp.py:32`、`tgapp.py:15`、`wecomapp.py:20`：`from chatapp_common import …`
  - `fsapp.py:82`：`from frontends.chatapp_common import …`
  - `stapp.py:18-21`：`import chatapp_common`、`from continue_cmd/btw_cmd/export_cmd import …`
  - `tuiapp_v2.py`：`29`(keysym)、`1415`(at_complete)、`1449`(import chatapp_common)、`1450`(chatapp_common)、`1451-1456`(btw/review/continue/workspace/export/worldline)、`2057/6134/6163/6308/6324/6363`(frontends.slash_cmds 惰性)
  - `tui_v3.py`：`35`(from frontends import at_complete, workspace_cmd)、`1376/3429`(frontends.slash_cmds)、`1411`(frontends continue_cmd)、`2338/4316/4479/4847/5830`(cost_tracker)、`2587/2684`(plan_state)、`4339/4596`(session_names)、`4349/4522`(continue_cmd)、`4668`(review_cmd)、`4688/4695`(slash_cmds)、`4866/5156`(export_cmd)、`4971`(btw_cmd)

  > 若 grep 命中 `stapp2.py`/`tuiapp.py`/`wechatapp.py` 中的 shared import，一并按规则改写。

- [ ] **Step 3: 按四条规则改写所有命中行**

  对 Step 2 命中的每一行，按下规则用 Edit 工具改写（**只改 import 行，不动其他**）：

  | 规则 | 原始形式 | 改为 |
  |---|---|---|
  | A | `from <MOD> import ...` | `from frontends.shared.<MOD> import ...` |
  | B | `import <MOD>` | `import frontends.shared.<MOD> as <MOD>` |
  | C | `from frontends import <MOD>[, <MOD2>]`（名字均为 shared 模块） | `from frontends.shared import <MOD>[, <MOD2>]` |
  | D | `from frontends.<MOD> import ...` | `from frontends.shared.<MOD> import ...` |

  其中 `<MOD>` ∈ 14 个 shared 模块名。

  示例改写：
  - `shared/chatapp_common.py:349` `from continue_cmd import handle_frontend_command as _handle_continue_frontend, install as _install_continue, reset_conversation as _reset_conversation`
    → `from frontends.shared.continue_cmd import handle_frontend_command as _handle_continue_frontend, install as _install_continue, reset_conversation as _reset_conversation`
  - `dcapp.py:11` `from chatapp_common import (` → `from frontends.shared.chatapp_common import (`
  - `tuiapp_v2.py:1449` `import chatapp_common` → `import frontends.shared.chatapp_common as chatapp_common`
  - `tuiapp_v2.py:1454` `import workspace_cmd` → `import frontends.shared.workspace_cmd as workspace_cmd`
  - `tui_v3.py:35` `from frontends import at_complete, workspace_cmd` → `from frontends.shared import at_complete, workspace_cmd`
  - `tui_v3.py:1376` `from frontends.slash_cmds import COMMIT_SIGNATURE_PROMPT` → `from frontends.shared.slash_cmds import COMMIT_SIGNATURE_PROMPT`

- [ ] **Step 4: 修 shared 文件中 `__file__` 项目根路径（加一层 parent）**

  对每个被搬入 `shared/` 的文件，查其 `__file__` 路径计算并加一层 parent。已知名点：

  ```bash
  grep -nE "__file__|_TEMP_DIR|_LOG_DIR|_REPO_ROOT|_ROOT|CODE_ROOT|PROJECT_ROOT" \
    frontends/shared/chatapp_common.py frontends/shared/export_cmd.py \
    frontends/shared/continue_cmd.py frontends/shared/session_names.py \
    frontends/shared/review_cmd.py frontends/shared/workspace_cmd.py frontends/shared/slash_cmds.py
  ```

  改写规则（每处加一层 parent，**不动指向 sibling 的路径**）：
  - `os.path.dirname(os.path.dirname(os.path.abspath(__file__)))`（=项目根）
    → 外面再包一层：`os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))`
  - `os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "temp")`（=项目根/temp）
    → `os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "temp")`
  - `Path(__file__).resolve().parent.parent`（slash_cmds `_ROOT`）
    → `Path(__file__).resolve().parent.parent.parent`

  已知具体点（逐一改）：
  - `shared/chatapp_common.py:4` `_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))` → 加一层 `os.path.dirname(...)`
  - `shared/chatapp_common.py:41` `PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))` → 同上
  - `shared/export_cmd.py:11` `_TEMP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'temp')` → 中段加一层 dirname
  - `shared/continue_cmd.py:5` 与 `shared/session_names.py:8`：`_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), …)` → 中段加一层 dirname
  - `shared/review_cmd.py:12` `CODE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))` → 加一层
  - `shared/workspace_cmd.py:38` `_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))` → 加一层
  - `shared/slash_cmds.py:94` `_ROOT = Path(__file__).resolve().parent.parent` → `.parent.parent.parent`

  > 注意：`slash_cmds.py` 内还有 A-class 字符串 `"frontends/conductor.py"` 与 picker 的 `rel = "frontends/" + p.name`——这些**留到 Task 9**（发现逻辑）与 Task 10 处理，本 task 不动。

- [ ] **Step 5: 验证 GREEN**

  ```bash
  python -m py_compile frontends/shared/*.py
  python -m py_compile frontends/dcapp.py frontends/dingtalkapp.py frontends/fsapp.py frontends/qqapp.py frontends/qtapp.py frontends/stapp.py frontends/stapp2.py frontends/tgapp.py frontends/tuiapp.py frontends/tuiapp_v2.py frontends/tui_v3.py frontends/wechatapp.py frontends/wecomapp.py
  python -c "import sys; sys.path.insert(0,'.'); import frontends.shared.chatapp_common, frontends.shared.slash_cmds, frontends.shared.worldline, frontends.shared.plan_state, frontends.shared.cost_tracker, frontends.shared.session_names, frontends.shared.keysym, frontends.shared.at_complete, frontends.shared.workspace_cmd, frontends.shared.continue_cmd, frontends.shared.btw_cmd, frontends.shared.review_cmd, frontends.shared.export_cmd, frontends.shared.model_cmd; print('shared import ok')"
  ```

  预期：全部无异常，输出 "shared import ok"。

  审计：确认无残留 flat shared import（除 `shared/` 内部已改写外）：

  ```bash
  grep -rnE "(^|[[:space:]])(import|from)[[:space:]]+(chatapp_common|slash_cmds|continue_cmd|btw_cmd|review_cmd|export_cmd|model_cmd|workspace_cmd|at_complete|worldline|plan_state|cost_tracker|session_names|keysym)\b" frontends/ | grep -v "frontends.shared"
  ```

  预期：无输出（全部已带 `frontends.shared`）。

- [ ] **Step 6: Commit**

  ```bash
  git add -A frontends/
  git commit -m "refactor(frontends): move shared modules into shared/ and rewrite imports"
  ```

---

### Task 3: 搬迁 bots/ + 修 bots 文件 __file__ 路径

**Files:**
- Move: `frontends/{qqapp,dcapp,tgapp,dingtalkapp,wechatapp,wecomapp,fsapp}.py` → `frontends/bots/`
- Modify（`__file__` 路径）：上述 7 文件中指向项目根 / 项目根`temp` 的计算

**Interfaces:** 消费 `frontends.shared.chatapp_common` 等（Task 2 已就绪，import 行无需再改）。

- [ ] **Step 1: git mv 7 个 bot 文件**

  ```bash
  cd frontends
  for f in qqapp dcapp tgapp dingtalkapp wechatapp wecomapp fsapp; do
      git mv "$f.py" "bots/$f.py"
  done
  cd ..
  ```

- [ ] **Step 2: 修每个 bot 文件的 `__file__` 项目根路径**

  对 7 个文件查 `__file__`/`_TEMP_DIR`/`PROJECT_ROOT`/`sys.path.insert`，把"项目根"或"项目根/temp"的计算加一层 parent。改写规则同 Task 2 Step 4（包一层 `os.path.dirname` 或 `join` 里加 `"..", ".."`）。

  已知具体点：
  - `bots/dcapp.py:9` `sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))` → 加一层 dirname
  - `bots/dcapp.py:29` `PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))` → 加一层
  - `bots/dingtalkapp.py:4`、`bots/qqapp.py:4`、`bots/tgapp.py:2`、`bots/wechatapp.py:6`、`bots/wecomapp.py:18`：`sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))` → 加一层
  - `bots/tgapp.py:3`、`bots/wechatapp.py:7`：`_TEMP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'temp')` → 中段加一层 dirname
  - `bots/wechatapp.py:435` `os.path.join(os.path.dirname(os.path.dirname(__file__)), 'temp', 'wechatapp.log')` → 中段加一层 dirname
  - `bots/fsapp.py:4-5` `PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))` 与 `sys.path.insert(0, PROJECT_ROOT)` → PROJECT_ROOT 加一层

  复核命令（应只剩"指向 sibling/自身目录"的路径，无需改）：

  ```bash
  grep -nE "__file__" frontends/bots/*.py
  ```

- [ ] **Step 3: 验证 GREEN**

  ```bash
  python -m py_compile frontends/bots/*.py
  python -c "import sys; sys.path.insert(0,'.'); 
  import frontends.bots.dcapp, frontends.bots.dingtalkapp, frontends.bots.fsapp, frontends.bots.qqapp, frontends.bots.tgapp, frontends.bots.wechatapp, frontends.bots.wecomapp
  print('bots import ok')" 2>&1 | tail -5
  ```

  > 注意：部分 bot 在 import 时可能尝试初始化外部连接（如读取 token/网络）。若报错源自"缺少运行时凭证/网络"而非 import 路径，视为环境问题，不阻断；只要错误不是 `ModuleNotFoundError: No module named 'chatapp_common'` 即说明 import 改写成功。`py_compile` 通过即保证语法与路径表达式正确。

- [ ] **Step 4: Commit**

  ```bash
  git add -A frontends/bots/
  git commit -m "refactor(frontends): move IM bot apps into bots/"
  ```

---

### Task 4: 搬迁 tui/ + 修 tui 文件 __file__ 路径

**Files:**
- Move: `frontends/{tuiapp,tuiapp_v2,tui_v3}.py` → `frontends/tui/`
- Modify（`__file__` 路径）：上述 3 文件

**Interfaces:** 消费 `frontends.shared.*`（Task 2 已就绪）。

- [ ] **Step 1: git mv**

  ```bash
  cd frontends
  git mv tuiapp.py tui/tuiapp.py
  git mv tuiapp_v2.py tui/tuiapp_v2.py
  git mv tui_v3.py tui/tui_v3.py
  cd ..
  ```

- [ ] **Step 2: 修 `__file__` 项目根路径**

  已知具体点（逐一加一层 parent）：
  - `tui/tuiapp.py:47` `ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))` → `os.path.join(os.path.dirname(__file__), "..", "..")`
  - `tui/tuiapp_v2.py:1418` `ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))` → `"..", ".."`
  - `tui/tuiapp_v2.py:1421` `FRONTENDS_DIR = os.path.dirname(os.path.abspath(__file__))`：此变量原指 `frontends/` 目录（用于 flat import 时的 sys.path）。现已改用包 import，该变量若仍被用于 `sys.path.insert(0, FRONTENDS_DIR)`（1423 行），**保留但在 Task 9 前无害**；但更干净的做法是删除 1421–1423 这三行（因为 flat import 已不存在）。**本 step 仅把 `FRONTENDS_DIR` 语义保持为"当前文件所在目录"，不删**——是否删除留待 grep 确认其无其他引用后，在 Step 3 决定。
  - `tui/tuiapp_v2.py:1574` `os.path.dirname(os.path.abspath(__file__)), "..", "temp", "tui_settings.json"` → 加一个 `".."`
  - `tui/tui_v3.py:18` `_proj_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))` → 加一层 dirname
  - `tui/tui_v3.py:19` `_front_dir = os.path.dirname(os.path.abspath(__file__))`（原指 `frontends/`，用于 flat import sys.path）：同上，保留为"当前目录"；若 1423-style `sys.path.insert` 依赖它做 flat import，因 flat import 已无对象，可保留无害。
  - `tui/tui_v3.py:52` `os.path.dirname(os.path.abspath(__file__)), "..", "temp", "tui_v3_settings.json"` → 加一个 `".."`
  - `tui/tui_v3.py:2002` `_ROOT = os.path.realpath(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))` → 加一层 dirname

  > 关于 `_front_dir`/`FRONTENDS_DIR` + 对应 `sys.path.insert`：重构后不再有 flat import，这些 sys.path 注入变成无的之矢。但删除它们属于"清理"边界外。本 plan 选择**保留不动**（不删行、不改其值指向），因为它们不会造成错误（向 sys.path 加一个存在的目录是无害的）。若 Step 3 grep 显示这些变量无其他引用，可在本 task 内删除以保持整洁——这是可选的，不强制。

  复核：

  ```bash
  grep -nE "__file__" frontends/tui/*.py
  ```

- [ ] **Step 3: 验证 GREEN**

  ```bash
  python -m py_compile frontends/tui/*.py
  python -c "import sys; sys.path.insert(0,'.'); import frontends.tui.tuiapp_v2" 2>&1 | tail -3
  python -c "import sys; sys.path.insert(0,'.'); import frontends.tui.tui_v3" 2>&1 | tail -3
  ```

  > Textual/平台相关 import 可能在无 GUI 环境报错；只要不是 `ModuleNotFoundError` 指向 shared 模块即视为路径改写成功。`py_compile` 通过为硬性门槛。

- [ ] **Step 4: Commit**

  ```bash
  git add -A frontends/tui/
  git commit -m "refactor(frontends): move TUI apps into tui/"
  ```

---

### Task 5: 搬迁 web/ + 修 stapp 文件 __file__ 路径

**Files:**
- Move: `frontends/{stapp,stapp2}.py` → `frontends/web/`
- Modify（`__file__` 路径）：`stapp.py`、`stapp2.py`

**Interfaces:** 消费 `frontends.shared.chatapp_common/continue_cmd/btw_cmd/export_cmd`（Task 2 已就绪）。

- [ ] **Step 1: git mv**

  ```bash
  cd frontends
  git mv stapp.py web/stapp.py
  git mv stapp2.py web/stapp2.py
  cd ..
  ```

- [ ] **Step 2: 修 `__file__` 项目根路径**

  已知点：
  - `web/stapp.py:10-12`：`script_dir = os.path.dirname(__file__)`；`sys.path.append(os.path.abspath(os.path.join(script_dir, '..')))`（指项目根）→ 改 `join(script_dir, '..', '..')`；`sys.path.append(os.path.abspath(script_dir))` 保留（指当前目录，无害）
  - `web/stapp2.py:9`：`sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))` → `'..', '..'`

  复核：

  ```bash
  grep -nE "__file__|script_dir|sys\.path" frontends/web/*.py
  ```

- [ ] **Step 3: 验证 GREEN**

  ```bash
  python -m py_compile frontends/web/*.py
  ```

  （streamlit 应用 import 需安装 streamlit，此处仅做编译检查；运行验证在 Task 11。）

- [ ] **Step 4: Commit**

  ```bash
  git add -A frontends/web/
  git commit -m "refactor(frontends): move Streamlit web apps into web/"
  ```

---

### Task 6: 搬迁桌面应用到 desktop/ + 修 __file__ 路径

**Files:**
- Move: `frontends/qtapp.py`、`frontends/desktop_pet_v2.pyw`、`frontends/desktop_bridge.py`、`frontends/chat_bubble.png`、`frontends/DESKTOP_PET_README.md`、`frontends/skins/` → `frontends/desktop/`
- 不动：`frontends/desktop/src-tauri/`、`frontends/desktop/static/`、`frontends/desktop/package.json`
- Modify（`__file__` 路径）：`qtapp.py`、`desktop_pet_v2.pyw`、`desktop_bridge.py`

**Interfaces:** `desktop_bridge.py` 消费项目根路径定位 `frontends/` 下各服务（B-class 发现，Task 9 处理）；`qtapp.py` 消费 `frontends.shared.chatapp_common`。

- [ ] **Step 1: git mv（Tauri 项目文件不动）**

  ```bash
  cd frontends
  git mv qtapp.py desktop/qtapp.py
  git mv desktop_pet_v2.pyw desktop/desktop_pet_v2.pyw
  git mv desktop_bridge.py desktop/desktop_bridge.py
  git mv chat_bubble.png desktop/chat_bubble.png
  git mv DESKTOP_PET_README.md desktop/DESKTOP_PET_README.md
  git mv skins desktop/skins
  cd ..
  ```

  > 确认 `desktop/` 下 `src-tauri/`、`static/`、`package.json` 路径未变：

  ```bash
  ls frontends/desktop/src-tauri/tauri.conf.json frontends/desktop/static frontends/desktop/package.json
  cat frontends/desktop/src-tauri/tauri.conf.json | grep frontendDist
  ```

  预期 `frontendDist` 仍为 `"../static"`，且 `static/` 仍是 `desktop/` 的直接子目录 → Tauri 构建路径不受影响。

- [ ] **Step 2: 修 `__file__` 项目根路径**

  已知点：
  - `desktop/qtapp.py:30` `sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))` → `'..', '..'`
  - `desktop/qtapp.py:2290` `os.path.dirname(os.path.dirname(__file__)), "memory"` → 加一层 dirname（指项目根/memory）
  - `desktop/desktop_pet_v2.pyw`：`grep -nE "__file__"` 查所有项目根/`skins`/`chat_bubble` 路径；指向 `skins/`、`chat_bubble.png` 的相对路径因这些资产与 `.pyw` 同迁入 `desktop/`、仍为同目录 → **无需改**；指向项目根的需加一层。
  - `desktop/desktop_bridge.py`：该文件用 `find_default_ga_root()` 等定位项目根（非纯 `__file__`），`grep -nE "__file__|APP_DIR|find_default"` 审视；凡纯靠 `__file__` 推项目根的加一层，靠运行时 root 发现的不动。

  复核：

  ```bash
  grep -nE "__file__" frontends/desktop/qtapp.py frontends/desktop/desktop_pet_v2.pyw frontends/desktop/desktop_bridge.py
  ```

  > `desktop_bridge.py` 内 `_SERVICE_KEYS` 的 6 个 key（`"frontends/qqapp.py"` 等）与 conductor 路径字符串属 A-class，**留到 Task 9** 一并更新（与发现逻辑同文件）。

- [ ] **Step 3: 验证 GREEN**

  ```bash
  python -m py_compile frontends/desktop/qtapp.py frontends/desktop/desktop_bridge.py
  python -c "import sys; sys.path.insert(0,'.'); import frontends.desktop.desktop_bridge" 2>&1 | tail -3
  ```

  （`desktop_pet_v2.pyw` 与 qtapp 需 PySide6，仅编译/按需 import。）

- [ ] **Step 4: Commit**

  ```bash
  git add -A frontends/desktop/
  git commit -m "refactor(frontends): move desktop apps and pet assets into desktop/"
  ```

---

### Task 7: 搬迁 conductor/ + 修 __file__ 路径 + 补 conductor_im_plugins 包判定

**Files:**
- Move: `frontends/conductor.py`、`frontends/conductor.html`、`frontends/conductor_im_plugins/` → `frontends/conductor/`
- Modify（`__file__` 路径）：`conductor.py`
- 视情况 Create：`frontends/conductor/conductor_im_plugins/__init__.py`

**Interfaces:** `conductor.py` 消费 `agentmain.Tau`（项目根在 sys.path 即可）；引用同目录 `conductor.html`、`conductor_im_plugins/`。

- [ ] **Step 1: git mv（html 与 plugins 与 .py 同迁，保持同目录）**

  ```bash
  cd frontends
  git mv conductor.py conductor/conductor.py
  git mv conductor.html conductor/conductor.html
  git mv conductor_im_plugins conductor/conductor_im_plugins
  cd ..
  ```

- [ ] **Step 2: 修 `conductor.py` 的 `__file__` 项目根路径**

  已知点：
  - `conductor/conductor.py:11` `ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))` → 加一层 dirname
  - `conductor/conductor.py:12` `if ROOT not in sys.path: sys.path.insert(0, ROOT)` → 随 ROOT 自动正确
  - `conductor/conductor.py:18` `HTML_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "conductor.html")` → **不改**（conductor.html 同迁，仍同目录）
  - `conductor/conductor.py:390` `IM_DIR = os.path.join(os.path.dirname(__file__), "conductor_im_plugins")` → **不改**（plugins 同迁，仍同目录）

- [ ] **Step 3: 判定 `conductor_im_plugins/` 是否需要 `__init__.py`**

  查 `conductor.py` 如何 import 插件：

  ```bash
  grep -nE "conductor_im_plugins|importlib|__import__|listdir" frontends/conductor/conductor.py | head
  ```

  - 若用 `importlib`/`listdir` 动态加载（按文件路径），**无需** `__init__.py`，尊重现状。
  - 若用 `from conductor_im_plugins import X` 式包 import，则在 `frontends/conductor/conductor_im_plugins/` 下 `: > __init__.py`。

  预期：根据 spec 已知该目录仅含 `_TEMPLATE.py`/`_email_example.py`/`_lark_example.py`，多为动态加载示例，多半无需 `__init__.py`。按 grep 结果决定。

- [ ] **Step 4: 验证 GREEN**

  ```bash
  python -m py_compile frontends/conductor/conductor.py
  python -c "import sys; sys.path.insert(0,'.'); import frontends.conductor.conductor" 2>&1 | tail -3
  ```

  （FastAPI import 需其已安装；`py_compile` 通过为硬性门槛。）

- [ ] **Step 5: Commit**

  ```bash
  git add -A frontends/conductor/
  git commit -m "refactor(frontends): move conductor app into conductor/"
  ```

---

### Task 8: 搬迁 acp/ + 修 __file__ 路径

**Files:**
- Move: `frontends/tau_acp_bridge.py` → `frontends/acp/tau_acp_bridge.py`
- Modify（`__file__`/`sys.path`）：`tau_acp_bridge.py`

**Interfaces:** 该桥接在 import `agentmain` 前重配 stdout，依赖项目根在 sys.path。

- [ ] **Step 1: git mv**

  ```bash
  git mv frontends/tau_acp_bridge.py frontends/acp/tau_acp_bridge.py
  ```

- [ ] **Step 2: 修 `sys.path` 项目根路径**

  已知点：
  - `acp/tau_acp_bridge.py:6` `sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))` → 加一层 dirname

  该文件还有 stdout 重配逻辑（跨平台，含 `sys.__stdout__.fileno()` 等）——**一律不动**，只改第 6 行的路径深度。

  复核：

  ```bash
  grep -nE "sys\.path|__file__|dirname" frontends/acp/tau_acp_bridge.py | head
  ```

- [ ] **Step 3: 验证 GREEN**

  ```bash
  python -m py_compile frontends/acp/tau_acp_bridge.py
  ```

  （该桥接运行需 ACP 客户端上下文，仅编译验证。）

- [ ] **Step 4: Commit**

  ```bash
  git add -A frontends/acp/
  git commit -m "refactor(frontends): move ACP bridge into acp/"
  ```

---

### Task 9: 重写自动发现逻辑（B-class）+ 更新发现相关 A-class 字符串

**Files:**
- Modify: `hub.pyw`（`discover_services`）
- Modify: `frontends/shared/slash_cmds.py`（`list_launchable_services` + `"frontends/conductor.py"` 字符串 + picker `rel` 拼接）
- Modify: `frontends/desktop/desktop_bridge.py`（`discover_im_services`、`discover_extra_services`、`_SERVICE_KEYS` 6 个 key、conductor 路径字符串）
- Modify: `frontends/shared/at_complete.py`（`@` 补全的 frontends 文件索引/重写逻辑）

**Interfaces:**
- Consumes：各载体子目录已就位（Task 3–8）。
- Produces：发现函数返回的服务 id/cmd 路径全部带子目录前缀；服务集合与 `/tmp/tau_discovery_baseline.json` 一致。

- [ ] **Step 1: 重写 `hub.pyw discover_services()` 扫描子目录**

  当前逻辑（`os.listdir(frontends)` 平铺 + `'app' in f` 过滤 + stapp 特判 streamlit）。改为遍历载体子目录：

  阅读现有实现：

  ```bash
  sed -n '18,40p' hub.pyw
  ```

  改写思路（保持过滤语义、仅改扫描范围与路径拼接）：
  - 将 `for f in sorted(os.listdir(frontends_dir)):` 改为遍历各载体子目录的 `.py`，例如：
    ```python
    for carrier in ("bots", "tui", "web", "desktop", "conductor", "acp"):
        cdir = os.path.join(frontends_dir, carrier)
        if not os.path.isdir(cdir): continue
        for f in sorted(os.listdir(cdir)):
            if not f.endswith('.py'): continue
            rel = f"frontends/{carrier}/{f}"   # 原 'frontends/' + f
            # 维持原有 EXCLUDES / 'app' in f / stapp 特判逻辑，基于 basename f
            ...
            cmd_streamlit = [sys.executable, '-m', 'streamlit', 'run', rel, '--server.headless=true']
            cmd_plain = [sys.executable, rel]
    ```
  - `EXCLUDES` 集合保持按 basename 过滤（`tuiapp.py` 仍排除；`chatapp_common.py`/`goal_mode.py` 已不在载体目录，其排除项变冗余但无害——以 Step 5 的集合 diff 为准增删）。

- [ ] **Step 2: 重写 `slash_cmds.list_launchable_services()` 同步扫描子目录**

  ```bash
  sed -n '325,445p' frontends/shared/slash_cmds.py
  ```

  将 `fe = Path(...)/"frontends"` 后的 `for p in sorted(fe.glob("*.py"))` 改为遍历各载体子目录：
  ```python
  for carrier in ("bots", "tui", "web", "desktop", "conductor", "acp"):
      for p in sorted((fe / carrier).glob("*.py")):
          ...
          rel = f"frontends/{carrier}/" + p.name   # 原 "frontends/" + p.name
  ```
  维持原 EXCLUDES/`'app' in name`/stapp 特判。同时更新文件内 A-class 字符串：
  - `frontends/conductor.py`（help 文本与启动逻辑）→ `frontends/conductor/conductor.py`
  - picker 中其他 `rel = "frontends/" + ...` 拼接 → 带载体前缀

- [ ] **Step 3: 重写 `desktop_bridge` 的两个发现函数 + 更新 `_SERVICE_KEYS`**

  ```bash
  sed -n '860,920p' frontends/desktop/desktop_bridge.py
  ```

  - `discover_im_services(ga_root)`：把 `d = ga_root/"frontends"; for f in os.listdir(d)` 改为扫 `ga_root/"frontends"/"bots"`；`rel = f"frontends/bots/{f}"`；`cmd` 用 `str(d_bots / f)`。
  - `discover_extra_services`：conductor 路径 `ga_root/"frontends"/"conductor.py"` → `ga_root/"frontends"/"conductor"/"conductor.py"`；其 id 与 cmd 中的 `"frontends/conductor.py"` → `"frontends/conductor/conductor.py"`。
  - `_SERVICE_KEYS`：6 个 key `"frontends/qqapp.py"` 等 → `"frontends/bots/qqapp.py"` 等。
  - docstring 示例（第 22–24、868–873 行附近）同步更新。

- [ ] **Step 4: 重写 `at_complete.py` 的 `@` 补全文件索引/重写**

  ```bash
  grep -nE "frontends|listdir|glob|walk|@frontends|rewrite|mention" frontends/shared/at_complete.py | head -30
  ```

  当前索引/重写识别 `@frontends/<file>.py`。改为识别 `@frontends/<carrier>/<file>.py`：索引构建时遍历各载体子目录收集 `.py`；重写时按新路径格式输出。具体行号以 grep 为准，改动限定在"扫描范围"与"路径字符串格式"，不动 fuzzy_rank 等纯逻辑。

- [ ] **Step 5: 验证发现集合 == 基线**

  ```bash
  python - <<'PY'
  import sys, json
  sys.path.insert(0, ".")
  out = {}
  from frontends.shared.slash_cmds import list_launchable_services
  out["slash_cmds"] = list_launchable_services()
  from frontends.desktop.desktop_bridge import discover_im_services, discover_extra_services
  from pathlib import Path
  root = Path(".")
  out["desktop_bridge_im"] = discover_im_services(root)
  out["desktop_bridge_extra"] = discover_extra_services(root)
  print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
  PY
  ```

  与 `/tmp/tau_discovery_baseline.json` 比对：
  - **服务 id 集合**（去掉路径前缀差异后按 basename 比较）必须一致。
  - 路径前缀应变为带载体子目录的形式。
  - 若集合有差（多/少某项），调整对应 `EXCLUDES`/`_SKIP`/特判，直到 basename 集合一致。

  hub.pyw 若基线为 `SKIPPED`：按 `discover_services` 现有过滤规则手工核对（EXCLUDES + `'app' in f` + stapp）覆盖的 basename 集合在子目录扫描下等价。

- [ ] **Step 6: 验证 GREEN**

  ```bash
  python -m py_compile hub.pyw frontends/shared/slash_cmds.py frontends/shared/at_complete.py frontends/desktop/desktop_bridge.py
  python -c "import sys; sys.path.insert(0,'.'); from frontends.shared.slash_cmds import list_launchable_services; print(len(list_launchable_services()), 'services')"
  ```

- [ ] **Step 7: Commit**

  ```bash
  git add hub.pyw frontends/shared/slash_cmds.py frontends/shared/at_complete.py frontends/desktop/desktop_bridge.py
  git commit -m "refactor(frontends): make app discovery scan carrier subdirs; update service id paths"
  ```

---

### Task 10: 更新外部启动器与文档的路径字符串（A-class）

**Files:**
- Modify: `tau_cli/cli.py`
- Modify: `launch.pyw`
- Modify: `README.md`
- Modify: `memory/review_sop.md`

**Interfaces:** 无（纯字符串/文档）。

- [ ] **Step 1: `tau_cli/cli.py`**

  ```bash
  grep -nE "FRONTENDS.*\.py|qtapp|tuiapp|tui_v3|stapp|conductor" tau_cli/cli.py
  ```

  改：
  - `{FRONTENDS}/qtapp.py` → `{FRONTENDS}/desktop/qtapp.py`
  - `{FRONTENDS}/tuiapp.py` → `{FRONTENDS}/tui/tuiapp.py`
  - `{FRONTENDS}/tuiapp_v2.py` → `{FRONTENDS}/tui/tuiapp_v2.py`
  - 若有 `tui_v3`/`stapp`/`conductor` 引用，相应补 `tui/`、`web/`、`conductor/`。

- [ ] **Step 2: `launch.pyw`**

  ```bash
  grep -nE "stapp|frontends" launch.pyw
  ```

  改：`os.path.join(frontends_dir, "stapp.py")` → `os.path.join(frontends_dir, "web", "stapp.py")`。

- [ ] **Step 3: `README.md`**

  ```bash
  grep -nE "frontends/[a-zA-Z_]+\.py" README.md
  ```

  对每条命中按目标归属补子目录：
  - `frontends/tui_v3.py`→`frontends/tui/tui_v3.py`；`tuiapp_v2.py`→`tui/tuiapp_v2.py`；`tuiapp.py`→`tui/tuiapp.py`
  - `tgapp/dcapp/fsapp/wechatapp/qqapp/wecomapp/dingtalkapp`→前缀 `bots/`
  - `stapp.py`→`web/stapp.py`；`qtapp.py`→`desktop/qtapp.py`；`conductor.py`→`conductor/conductor.py`

  > README 中 `GenericAgent.exe`/`TAU.exe`/`launch.pyw` 等非 `.py` 路径不动。

- [ ] **Step 4: `memory/review_sop.md`**

  ```bash
  grep -nE "frontends/review_cmd\.py" memory/review_sop.md
  ```

  改：`frontends/review_cmd.py` → `frontends/shared/review_cmd.py`。

- [ ] **Step 5: Commit**

  ```bash
  git add tau_cli/cli.py launch.pyw README.md memory/review_sop.md
  git commit -m "docs: update frontends/ paths for new subdirectory layout"
  ```

---

### Task 11: 最终验证 + 残留旧路径审计

**Files:** 无新建；仅验证与可能的零星修正。

- [ ] **Step 1: 全仓审计无残留 flat 路径/import**

  ```bash
  echo "=== 残留 flat shared import（应为空）==="
  grep -rnE "(^|[[:space:]])(import|from)[[:space:]]+(chatapp_common|slash_cmds|continue_cmd|btw_cmd|review_cmd|export_cmd|model_cmd|workspace_cmd|at_complete|worldline|plan_state|cost_tracker|session_names|keysym)\b" frontends/ tau_cli/ *.py *.pyw 2>/dev/null | grep -v "frontends.shared"
  echo "=== 残留 'frontends/<flat>.py' 旧路径字符串（应为空，除注释/历史 changelog）==="
  grep -rnE "frontends/(tui_v3|tuiapp_v2|tuiapp|tgapp|dcapp|fsapp|wechatapp|qqapp|wecomapp|dingtalkapp|stapp|stapp2|qtapp|conductor|tau_acp_bridge|chatapp_common|slash_cmds|continue_cmd|btw_cmd|review_cmd|export_cmd|model_cmd|workspace_cmd|at_complete|worldline|plan_state|cost_tracker|session_names|keysym)\.py" . 2>/dev/null | grep -vE "frontends/(bots|tui|web|desktop|conductor|acp|shared)/" | grep -v "__pycache__"
  ```

  预期：第一段无输出；第二段仅允许 README 的历史 changelog 条目（如"2026-05-23 TUI v3 released（frontends/tui_v3.py）"这类历史记录）——这些是历史事实陈述，不改。若出现非 changelog 的活引用，回到对应 Task 修正。

- [ ] **Step 2: import 冒烟（全部载体可被 import 或编译）**

  ```bash
  python -m py_compile $(git ls-files 'frontends/*.py' 'frontends/**/*.py')
  python -c "import sys; sys.path.insert(0,'.')
  import frontends.shared.chatapp_common, frontends.shared.slash_cmds, frontends.shared.worldline
  print('shared ok')"
  ```

- [ ] **Step 3: 可运行入口冒烟（环境允许时）**

  逐项试启动（若环境缺依赖则跳过该项并注明）：

  ```bash
  # TUI（最可能可跑）
  timeout 5 python frontends/tui/tui_v3.py --help 2>&1 | tail -5 || echo "tui_v3 needs tty/streamlit, skip"
  # conductor
  timeout 5 python frontends/conductor/conductor.py --no-browser 2>&1 | head -5 & sleep 3; kill %1 2>/dev/null
  # tau cli dry
  python -m tau_cli --help 2>&1 | tail -5
  ```

  预期：`tau --help` 列出的命令路径均指向新子目录结构；tui/conductor 不报 `ModuleNotFoundError`。

- [ ] **Step 4: 发现集合最终确认**

  重跑 Task 9 Step 5 的脚本，确认输出稳定且与基线 basename 集合一致。

- [ ] **Step 5: 收尾 Commit（若有修正）**

  ```bash
  git add -A
  git commit -m "refactor(frontends): final verification fixups" || echo "nothing to commit"
  ```

---

## Self-Review

**1. Spec coverage**
- 目录树（spec §3）：Task 1 骨架 + Task 2–8 各载体 → 全覆盖。
- import 改造规则（spec §4.1/4.2）：Task 2 四条规则 + `__file__` 修复 → 全覆盖；`__init__.py` 留空见 Task 1。
- 外部引用 A-class（spec §5.1）：Task 10（启动器+文档）+ Task 9（发现相关字符串）→ 全覆盖。
- 外部引用 B-class 发现逻辑（spec §5.2 四处）：Task 9 Step 1–4 → hub/slash_cmds/desktop_bridge/at_complete 全覆盖。
- 验收标准（spec §6）：Task 11 Step 1–4 对应"无残留/import/发现集合/Tauri 不动" → 全覆盖。Tauri 不动由 Task 6 Step 1 校验。
- 风险缓解（spec §7）：grep 审计贯穿各 Task；发现集合 diff 在 Task 1 捕获、Task 9/11 比对 → 覆盖。

**2. Placeholder scan**：无 TBD/TODO；每步含具体命令或改写规则与已知行点。`stapp2/tuiapp/wechatapp` 的 shared import 以 grep 复核命令显式覆盖（非占位）。`conductor_im_plugins/__init__.py` 以 grep 判定规则给出明确二选一（非占位）。

**3. Type/命名一致性**：shared 14 模块名在全 plan 一致；载体目录名 `bots/tui/web/desktop/conductor/acp/shared` 全篇一致；`_SERVICE_KEYS`、`EXCLUDES`、`_SKIP` 等沿用原文件既有名称。

**4. 顺序正确性**：Task 2 先于 3–8（apps 依赖 shared 绝对路径）；Task 9 后于 3–8（发现需扫描已就位的子目录）；Task 10 后于所有搬移。每 Task 末 GREEN（编译/import 通过）。
