# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目定位

TAU 是一个**极简、自演化**的自主 agent 框架。核心约 3K 行：一个 ~100 行的 agent loop + 9 个原子工具。设计哲学是「不预置技能，靠使用进化」——每次完成新任务，执行路径会被固化进 `memory/`，逐步长出专属技能树。

Python 3.10–3.13（**不要用 3.14**，与 pywebview 等依赖不兼容）。核心代码注释以中文为主。

## 常用命令

```bash
# 安装（故意做选择性依赖，不要一次装全）
uv venv && uv pip install -e ".[ui]"                 # 核心 + 桌面/TUI
uv pip install -e ".[all-frontends]"                 # 仅当需要 IM 机器人时

# 首次配置（生成 .tau/taukey.py，或交互向导）
cp assets/taukey_template.py .tau/taukey.py
python assets/configure_taukey.py

# 运行
./tau cli                    # = python agentmain.py，交互式 CLI（最轻量）
./tau list                   # 列出所有注册前端/命令
./tau gui / tui / hub / launch   # 各前端入口

# agentmain.py 的三种运行模式
python agentmain.py                              # 交互 REPL
python agentmain.py --func prompt.md             # 纯函数：读 prompt → 写 prompt.out.txt → 退出
python agentmain.py --task IODIR --input ...     # 子代理任务模式（先读 memory/subagent.md）
python agentmain.py --reflect reflect/xxx.py     # 反射模式：循环调用脚本 check() 触发任务

# 开发期热重载：改了 taukey.py 不用重启，下次调用自动 reload（按 mtime 检测）。
```

**无测试、无 lint 基建**：仓库没有 pytest/unittest/ruff 配置。验证靠实际跑 `agentmain.py` 或对应前端。提交前必读 [CONTRIBUTING.md](CONTRIBUTING.md) 与 [memory/code_review_principles.md](memory/code_review_principles.md)——PR 走严格自动 review，大多数 AI 生成代码原样过不了。

## 架构（big picture）

核心是一个**分层、可替换后端**的 agent loop。理解以下五层就能定位几乎所有改动：

```
agent_runner_loop()          ← agent_loop.py：通用 LLM↔tool 调度循环（与厂商无关）
        │ 调用
        ▼
client.chat() / .dispatch()  ← llmcore.py（Session/Client）+ tau.py（TauHandler.do_*）
        │                        handler 按 tool_name 路由到 do_code_run / do_file_read / ...
        ▼
Tau.put_task() → run()       ← agentmain.py：任务队列、线程、slash 命令、前端对接
        │
        ▼
apps/*  &  reflect/*         ← 前端（人机界面）& 反射脚本（自驱触发器）
```

### 1. `agent_loop.py` — 通用调度循环（~100 行，不要膨胀）

`agent_runner_loop(client, system_prompt, user_input, handler, tools_schema, ...)` 是**唯一**的 agent 主循环。它只认 `client.chat()` 和 `handler.dispatch()` 两个接口，不依赖任何具体厂商协议。新功能应通过新增 `do_<tool>` 方法或新 Session 类接入，**而不是在这里加分支**。注意：循环每轮把上一轮的 `tool_results` 作为新 user message 发回，完整 history 由 Session 自己保存（不在 messages 里累积）。

- `BaseHandler.dispatch()` 按 `do_<tool_name>` 约定方法路由；工具实现是 generator，通过 `StepOutcome(data, next_prompt, should_exit)` 告诉循环下一步。
- 历史 token 压缩在 `llmcore.compress_history_tags()` / `trim_messages_history()` 里，按 `context_win` 自动裁剪。

### 2. `llmcore.py` — Session / Client 层（厂商抽象）

两套工具协议、四类 Session，**由 taukey.py 里的变量名决定类型**（不是模型名）：

| taukey 变量名含 | Session 类 | 工具协议 |
|---|---|---|
| `native` + `claude` | `NativeClaudeSession` | API 原生 tool 字段（**推荐**） |
| `native` + `oai` | `NativeOAISession` | API 原生 tool 字段 |
| `mixin` | `MixinSession` | 多 session 故障转移（成员须同组：全 native 或全非 native） |
| `claude` / `oai`（无 `native`） | `ClaudeSession` / `LLMSession` | 文本协议工具（**deprecated**） |

`ToolClient` / `NativeToolClient` 把 Session 包成统一的 `client.chat()` 接口。`resolve_client(cfg_name)` 是按名字查 session 的入口。`apibase` 有自动补全规则（见 `taukey_template.py` 注释）。改 LLM 层时务必保持「新协议 = 加新 Session 子类」，不要在现有 Session 里堆 if-else。

### 3. `tau.py` — `TauHandler` 工具实现 + 系统工具函数

`TauHandler(BaseHandler)` 实现全部 `do_*` 工具（`do_code_run` / `do_file_read` / `do_file_patch` / `do_file_write` / `do_web_scan` / `do_web_execute_js` / `do_ask_user` / `do_no_tool` / `do_start_long_term_update` / `do_update_working_checkpoint`）。工具 schema 在 `assets/tools_schema.json`（Linux/macOS 走 bash，Windows 走 powershell——加载时自动替换）；GLM/MiniMax/Kimi 走 `tools_schema_cn.json`。

模块顶部还有框架内处处复用的物理工具函数：`code_run`（子进程执行器，cwd 默认 `temp/`）、`file_read` / `file_patch` / `smart_format` / `consume_file` / `get_global_memory` 等。

**web 工具底层在两个根级模块**：`TMWebDriver.py`（WebSocket + bottle 服务，注入**真实浏览器**保留登录态，`tau.py` 内懒加载 `from TMWebDriver import TMWebDriver`）+ `simphtml.py`（页面 HTML 精简与 `execute_js_rich`，向页面注入 `optHTML` / `createEnhancedDOMCopy` JS 产出 token 高效快照）。`do_web_scan` / `do_web_execute_js` 都经此路径；改浏览器侧逻辑先读 [memory/tmwebdriver_sop.md](memory/tmwebdriver_sop.md)。

### 4. `agentmain.py` — `Tau` 编排器

`Tau` 类是单一入口：维护 `task_queue`、工作线程、llm client 列表与切换（`next_llm`）、slash 命令（`/session.xxx=yyy`、`/resume`）、长 prompt 落盘。`run()` 从队列取任务，构造 `TauHandler`，喂给 `agent_runner_loop`，把 generator 产出的 chunk 推回 `display_queue` 供前端消费。

**SDK 用法**：`agent = Tau(); threading.Thread(target=agent.run, daemon=True).start(); q = agent.put_task(prompt)`——所有前端（CLI、TUI、bot、conductor）都是这么对接的。

### 5. `apps/` 前端 与 `reflect/` 反射脚本

- **`apps/<carrier>/`**：`bots/`（tg/qq/wechat/discord/dingtalk/wecom/feishu）、`desktop/`（qtapp、desktop_pet、tauri `src-tauri/`）、`tui/`（`tui_v3.py` 滚屏回看版、`tuiapp_v2.py` Textual 版）、`web/`（streamlit `stapp.py`）、`conductor/`（多 subagent 编排）、`acp/`（协议桥）、`shared/`（所有前端共用的 slash 命令、`worldline`、`plan_state`、`cost_tracker` 等）。
- **`reflect/*.py`** 契约：暴露 `check() -> str|None`（返回值即下一个任务 prompt）、`INTERVAL`（秒）、可选 `init(args_dict)` / `on_done(result)` / `ONCE=True`。`--reflect` 模式会在外层循环轮询，并在 mtime 变化时热重载脚本。内置：`scheduler.py`（cron）、`goal_mode.py`、`autonomous.py`、`checklist_master.py`、`agent_team_worker.py`。新增自驱模式 = 往 `reflect/` 丢一个脚本，不要改 agentmain。

## 自演化记忆系统（`memory/`）

这是 TAU 的核心机制，**不是普通文档目录**——里面的内容会被注入到每个 turn 的系统 prompt（见 `tau.py:get_global_memory()`）。层级（详见 [memory/memory_management_sop.md](memory/memory_management_sop.md)）：

- **L1** `global_mem_insight.txt`：≤30 行索引层，场景关键词 → 记忆定位 + 红线 RULES。
- **L2** `global_mem.txt`：环境事实库（路径、凭证、配置）。
- **L3** `memory/*.md` / `*.py`：任务级 SOP 与高复用工具脚本。
- **L4** `L4_raw_sessions/`：历史会话归档。

硬约束：**No Execution, No Memory**（只记工具验证过的事实）；不存易变状态（PID、时间戳、临时 session id）；L1 只放指针不写细节。改记忆要极度小心——能 `file_patch` 就不要 overwrite，改不动宁可不改。

## 插件 / Hooks（`plugins/`）

`plugins/hooks.py` 提供事件注册：`@register(event)` 装饰函数，`trigger(event, ctx)` 在钩子点调用。事件包括 `agent_before/after`、`turn_before/after`、`llm_before/after`、`tool_before/after`。`agentmain.py` 启动时 `discover_and_load()` 自动导入 `plugins/*.py`（以 `_` 开头的跳过）。内置 `langfuse_tracing.py`、`project_mode.py`。新增横切关注点（观测、审计）走插件，**不要塞进核心循环**。

## 重要约定与坑

- **Let it crash**：大半径错误显式中断、快失败；零半径错误静默放过。禁止到处 try-catch——会把真正该暴露的问题吞掉（见 [memory/code_review_principles.md](memory/code_review_principles.md) 第十四条）。
- **自解释、极简注释**：核心刻意压短，注释只写在真正难懂处。改核心时，行数应「持平或更少」，不是越长越好。
- **`sys.path` 改写**：多个模块（`tau_cli/__init__.py`、`agentmain.py`、`llmcore.py`）都会把项目根插入 `sys.path`，因为核心是平铺的根级 `py-modules` 而非 package。改导入结构时留意这点。
- **`tau_cli`** 通过 importlib 从根 `tau.py` 重新导出 `TauHandler` 等符号——根 `tau.py` 既是库也是脚本。
- **`.tau/` 被 gitignore**：真实 `taukey.py`（含密钥）只放这里；模板在 `assets/taukey_template*.py`。同理 `.claude/settings.local.json` 也不入库。
- **国际化**：`TAU_LANG=zh|en` 切换 `sys_prompt` / schema / 模板的后缀。zh 为默认。
- **代码即文档**：大部分高级模式（reflect / plan / goal / hive / conductor / morphling）故意没有独立手册——让 agent 读自己的源码自解释。改动这些模式时保持它们的「向 agent 自描述」特性。
