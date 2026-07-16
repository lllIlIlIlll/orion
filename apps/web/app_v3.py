import os, sys
_HERE = os.path.dirname(os.path.abspath(__file__))
_r = os.path.abspath(os.path.dirname(__file__))
while _r != os.path.dirname(_r) and not os.path.exists(os.path.join(_r, 'pyproject.toml')):
    _r = os.path.dirname(_r)
if _r not in sys.path:
    sys.path.insert(0, _r)

import os, sys
import html
if sys.stdout is None: sys.stdout = open(os.devnull, "w")
if sys.stderr is None: sys.stderr = open(os.devnull, "w")
try: sys.stdout.reconfigure(errors='replace')
except: pass
try: sys.stderr.reconfigure(errors='replace')
except: pass

import streamlit as st
import time, re, threading, queue
from datetime import datetime
from agentmain import Tau

st.set_page_config(page_title="Tau", layout="wide")

DESIGN_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Space+Mono&display=swap');

*, *::before, *::after { box-sizing: border-box; }

:root {
  --primary:    #1A1A1A;
  --secondary:  #C9B99A;
  --tertiary:   #D97757;
  --tertiary-h: #E8896A;
  --neutral:    #FAF9F7;
  --surface:    #FFFFFF;
  --border:     #E0DDD8;
  --user-bg:    #F0EDE8;
  --font:       'Inter', sans-serif;
  --mono:       'Space Mono', monospace;
  --r-sm: 6px; --r-md: 12px; --r-lg: 20px; --r-full: 9999px;
  --sp-xs:4px; --sp-sm:8px; --sp-md:16px; --sp-lg:24px; --sp-xl:32px;
}

/* ── Global ── */
html, body, [data-testid="stAppViewContainer"], .stApp {
    background-color: var(--neutral) !important;
    color: var(--primary) !important;
    font-family: var(--font) !important;
    width: 100% !important;
    min-width: 0 !important;
    overflow-x: hidden !important;
}

/* ── Hide Streamlit chrome ── */
[data-testid="stToolbar"] { visibility: hidden !important; }
[data-testid="stDecoration"], #MainMenu { display: none !important; }
[data-testid="stHeader"], header[data-testid="stHeader"] {
    background-color: var(--neutral) !important;
    border-bottom: 1px solid var(--border) !important;
    height: 0 !important; min-height: 0 !important; overflow: hidden !important;
}

/* ── Sidebar ── */
[data-testid="stSidebar"], section[data-testid="stSidebar"] {
    background-color: var(--neutral) !important;
    border-right: 1px solid var(--border) !important;
    width: 248px !important; min-width: 248px !important; max-width: 248px !important;
}
[data-testid="stSidebarContent"] {
    padding: var(--sp-lg) var(--sp-md) !important;
    display: flex !important; flex-direction: column !important; gap: var(--sp-md) !important;
    min-height: 100vh !important;
}
/* Push session info section to bottom */
.tau-sidebar-spacer { flex: 1 1 auto !important; min-height: 12px; }

/* Brand */
.tau-brand {
    display: flex; flex-direction: column; align-items: center;
    gap: 6px; padding-bottom: var(--sp-md); border-bottom: 1px solid var(--border);
}
.tau-brand-logo {
    width: 44px; height: 44px; border-radius: var(--r-md);
    background: var(--tertiary);
    display: flex; align-items: center; justify-content: center;
    font-family: var(--mono); font-size: 1rem; font-weight: 700;
    color: #fff; letter-spacing: 0.04em;
    box-shadow: 0 2px 8px rgba(217,119,87,0.25);
}
.tau-brand-name {
    font-family: var(--mono); font-size: 0.72rem;
    letter-spacing: 0.1em; text-transform: uppercase; color: var(--secondary);
}

/* Sidebar sections */
.tau-sidebar-title {
    font-family: var(--mono); font-size: 0.68rem;
    letter-spacing: 0.05em; text-transform: uppercase;
    color: var(--secondary); padding: 0 var(--sp-sm);
    margin-top: var(--sp-sm);
}
.tau-sidebar-row {
    display: flex; flex-direction: column; gap: 6px;
    padding: 10px 12px; border-radius: var(--r-sm);
    background: var(--surface); border: 1px solid var(--border);
    margin-bottom: 6px;
}
.tau-sidebar-row label {
    font-size: 0.7rem; color: var(--secondary);
    font-family: var(--mono); letter-spacing: 0.03em;
}
.tau-val { font-size: 0.82rem; font-weight: 500; display: flex; align-items: center; gap: 6px; min-width: 0; }
.tau-llm-name {
    font-family: var(--mono); font-size: 0.78rem;
    color: var(--primary); font-weight: 500;
    word-break: break-all; line-height: 1.45;
    display: block;
}
.tau-badge {
    display: inline-flex; align-items: center; gap: 4px;
    font-family: var(--mono); font-size: 0.62rem; letter-spacing: 0.03em;
    padding: 2px 8px; border-radius: var(--r-full);
    background: rgba(217,119,87,0.1); color: var(--tertiary);
    border: 1px solid rgba(217,119,87,0.25);
    flex-shrink: 0; white-space: nowrap;
}
.tau-badge::before {
    content: ''; width: 5px; height: 5px;
    border-radius: var(--r-full); background: var(--tertiary); display: inline-block;
    animation: tau-pulse 2s infinite;
}
@keyframes tau-pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }

/* Sidebar buttons */
[data-testid="stSidebar"] .stButton > button {
    font-family: var(--font) !important; font-size: 0.82rem !important;
    font-weight: 500 !important; padding: 8px 14px !important;
    border-radius: var(--r-sm) !important;
    border: 1px solid var(--border) !important;
    width: 100% !important; transition: background .2s !important;
    background: transparent !important; color: var(--primary) !important;
}
[data-testid="stSidebar"] .stButton > button:hover { background: var(--user-bg) !important; }
[data-testid="stSidebar"] .stButton > button[kind="primary"],
[data-testid="stSidebar"] .stButton > button[data-testid="stBaseButton-primary"] {
    background: var(--tertiary) !important; color: #fff !important;
    border-color: var(--tertiary) !important;
}
[data-testid="stSidebar"] .stButton > button[kind="primary"]:hover,
[data-testid="stSidebar"] .stButton > button[data-testid="stBaseButton-primary"]:hover {
    background: var(--tertiary-h) !important;
}

/* Sidebar selectbox */
[data-testid="stSidebar"] [data-baseweb="select"] > div {
    background: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--r-sm) !important;
    box-shadow: none !important;
}
[data-testid="stSidebar"] [data-baseweb="select"] > div:focus-within {
    border-color: var(--tertiary) !important;
    box-shadow: 0 0 0 3px rgba(217,119,87,0.12) !important;
}
[data-testid="stSidebar"] [data-baseweb="select"] span,
[data-testid="stSidebar"] [data-baseweb="select"] div {
    color: var(--primary) !important; font-family: var(--font) !important;
    font-size: 0.82rem !important;
}
[data-testid="stSidebar"] label, [data-testid="stSidebar"] .stMarkdown p,
[data-testid="stSidebar"] p { color: var(--secondary) !important; font-size: 0.72rem !important; }

/* Dropdown list */
[role="listbox"] {
    background: var(--surface) !important; border: 1px solid var(--border) !important;
    border-radius: var(--r-md) !important;
    box-shadow: 0 4px 16px rgba(26,26,26,0.08) !important;
    font-family: var(--font) !important; font-size: 0.82rem !important;
}
[role="option"] {
    color: var(--primary) !important; background: transparent !important;
    border-radius: var(--r-sm) !important;
}
[role="option"]:hover, [role="option"][aria-selected="true"] { background: var(--user-bg) !important; }

/* ── Message HTML classes — responsive to viewport ── */
.tau-msg {
    display: flex; gap: var(--sp-md); align-items: flex-start;
    padding: 0 max(20px, 3vw); margin-bottom: var(--sp-lg);
    width: 100%;
}
.tau-msg.user { flex-direction: row-reverse; }
.tau-avatar {
    width: 32px; height: 32px; border-radius: var(--r-full); flex-shrink: 0;
    display: flex; align-items: center; justify-content: center;
    font-size: 0.78rem; font-weight: 600; font-family: var(--mono);
}
.tau-avatar.agent { background: var(--tertiary); color: #fff; }
.tau-avatar.user { background: var(--user-bg); border: 1px solid var(--border); color: var(--primary); }
.tau-msg-wrap {
    display: flex; flex-direction: column; gap: 4px;
    min-width: 0;
}
/* User bubble: hugs content, capped, right-aligned */
.tau-msg.user .tau-msg-wrap {
    align-items: flex-end;
    max-width: min(75%, 760px);
}
/* Agent bubble: flex-grow fills the row so its right edge aligns with the
 * user bubble's right edge; the left (start) position stays after the avatar.
 * margin-right mirrors the user-side avatar(32px) + gap(--sp-md=16px) so both
 * right edges land on one vertical line. flex-grow is required — max-width
 * alone only caps width, it does not stretch the bubble to that width. */
.tau-msg:not(.user) .tau-msg-wrap {
    flex: 1 1 auto;
    margin-right: calc(32px + var(--sp-md));
}
/* Typing indicator stays compact — does not stretch to full width */
.tau-msg:not(.user) .tau-bubble:has(.tau-typing) { align-self: flex-start; }
.tau-msg-meta { font-family: var(--mono); font-size: 0.65rem; color: var(--secondary); letter-spacing: 0.03em; }
.tau-bubble {
    padding: var(--sp-md) var(--sp-lg); border-radius: var(--r-lg);
    font-size: 0.92rem; line-height: 1.65;
}
.tau-bubble.agent {
    background: var(--surface); border: 1px solid var(--border);
    border-top-left-radius: var(--r-sm);
}
.tau-bubble.user { background: var(--user-bg); border-top-right-radius: var(--r-sm); }
.tau-bubble p { margin: 0; }
.tau-bubble p + p { margin-top: var(--sp-sm); }
.tau-bubble strong { color: var(--tertiary); }
.tau-bubble code {
    font-family: var(--mono); font-size: 0.78rem;
    background: var(--neutral); padding: 2px 6px;
    border-radius: 4px; border: 1px solid var(--border);
}
.tau-bubble pre {
    background: var(--neutral); border: 1px solid var(--border);
    border-radius: var(--r-sm); padding: var(--sp-md); overflow-x: auto;
    margin: var(--sp-sm) 0;
}
.tau-bubble pre code { background: none; border: none; padding: 0; }
.tau-bubble ul, .tau-bubble ol { padding-left: 1.4em; margin: var(--sp-sm) 0; }
.tau-bubble li { margin-bottom: 2px; }

/* System message */
.tau-sys-msg { display: flex; justify-content: center; margin-bottom: var(--sp-lg); }
.tau-sys-msg span {
    font-family: var(--mono); font-size: 0.68rem; color: var(--secondary);
    letter-spacing: 0.03em; background: var(--surface); border: 1px solid var(--border);
    padding: 4px 12px; border-radius: var(--r-full);
}

/* Typing indicator */
.tau-typing { display: flex; gap: 5px; align-items: center; padding: 4px 2px; }
.tau-typing span {
    width: 6px; height: 6px; border-radius: var(--r-full);
    background: var(--secondary); animation: tau-bounce 1.2s infinite; display: inline-block;
}
.tau-typing span:nth-child(2) { animation-delay: .2s; }
.tau-typing span:nth-child(3) { animation-delay: .4s; }
@keyframes tau-bounce { 0%,60%,100% { transform: translateY(0); } 30% { transform: translateY(-5px); } }

/* ── Chat input ── */
[data-testid="stChatInput"] > div {
    background: var(--surface) !important; border: 1px solid var(--border) !important;
    border-radius: var(--r-md) !important; box-shadow: none !important;
}
[data-testid="stChatInput"] [data-baseweb="textarea"],
[data-testid="stChatInput"] [data-baseweb="base-input"] {
    background: transparent !important;
}
[data-testid="stChatInput"] > div:focus-within {
    border-color: var(--tertiary) !important;
    box-shadow: 0 0 0 3px rgba(217,119,87,0.12) !important;
}
[data-testid="stChatInput"] textarea {
    font-family: var(--font) !important; font-size: 0.92rem !important;
    color: var(--primary) !important; background: transparent !important;
    caret-color: var(--primary) !important;
}
[data-testid="stChatInput"] textarea::placeholder { color: var(--secondary) !important; opacity: 0.8 !important; }
[data-testid="stChatInput"] button, [data-testid="stChatInputSubmitButton"] {
    background: var(--tertiary) !important; border-radius: var(--r-sm) !important;
    color: #fff !important;
}
[data-testid="stChatInput"] button:hover { background: var(--tertiary-h) !important; }

/* Input hint */
[data-testid="stBottomBlockContainer"] { background: var(--neutral) !important; }
[data-testid="stBottomBlockContainer"]::after {
    content: 'ENTER 发送  ·  SHIFT+ENTER 换行';
    display: block; text-align: center;
    font-family: 'Space Mono', monospace;
    font-size: 0.65rem; color: #C9B99A;
    letter-spacing: 0.03em; margin-top: 4px; padding-bottom: 8px;
}

/* Stop button — bottom-right corner, doesn't block content.
 * Selector identifies the small container holding ONLY the stop button:
 * excludes any block that contains real messages (.tau-msg) or the chat input. */
.stop-btn-anchor { display: none !important; }
[data-testid="stElementContainer"]:has(.stop-btn-anchor) {
    height: 0 !important; min-height: 0 !important;
    margin: 0 !important; padding: 0 !important; overflow: visible !important;
}
[data-testid="stVerticalBlock"]:has(.stop-btn-anchor):not(:has(.tau-msg)):not(:has([data-testid="stChatInput"])) {
    position: fixed !important; bottom: 6.5rem !important;
    right: 32px !important; left: auto !important; transform: none !important;
    z-index: 1000 !important; width: auto !important; background: transparent !important;
    pointer-events: none !important; gap: 0 !important;
}
[data-testid="stVerticalBlock"]:has(.stop-btn-anchor):not(:has(.tau-msg)):not(:has([data-testid="stChatInput"])) > * { pointer-events: auto !important; }
[data-testid="stVerticalBlock"]:has(.stop-btn-anchor):not(:has(.tau-msg)):not(:has([data-testid="stChatInput"])) [data-testid="stButton"] > button {
    border-radius: var(--r-full) !important;
    background: rgba(217,119,87,0.95) !important; border-color: rgba(217,119,87,0.95) !important;
    color: #fff !important; font-size: 0.8rem !important; font-weight: 500 !important;
    padding: 0.4rem 1rem !important;
    box-shadow: 0 4px 14px rgba(217,119,87,0.35) !important;
    backdrop-filter: blur(8px) !important;
}

/* ── Main content area — fill remaining width, inner items centered ── */
[data-testid="stMainBlockContainer"] {
    padding-top: var(--sp-xl) !important;
    padding-left: 0 !important; padding-right: 0 !important;
    max-width: 100% !important;
    width: 100% !important;
    margin: 0 !important;
}
[data-testid="stMain"] {
    width: auto !important;
    min-width: 0 !important;
}
[data-testid="stMarkdownContainer"] { margin: 0 !important; padding: 0 !important; }
[data-testid="stElementContainer"] { margin-bottom: 0 !important; }

/* Messages & input fill main area, internal max-width controls reading width */
.tau-msg, .tau-sys-msg {
    max-width: 100% !important;
    width: 100% !important;
}
[data-testid="stBottomBlockContainer"] [data-testid="stChatInput"] {
    max-width: min(920px, 100%) !important;
    margin-left: auto !important;
    margin-right: auto !important;
}
[data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] {
    width: 100% !important;
    max-width: 100% !important;
}

/* ── Markdown tables inside agent bubbles ── */
.tau-bubble table {
    border-collapse: collapse; margin: var(--sp-sm) 0;
    width: 100%; font-size: 0.86rem;
}
.tau-bubble th, .tau-bubble td {
    border: 1px solid var(--border); padding: 6px 10px;
    text-align: left;
}
.tau-bubble th {
    background: var(--neutral); font-weight: 600; color: var(--primary);
}
.tau-bubble blockquote {
    border-left: 3px solid var(--tertiary);
    padding-left: var(--sp-md); margin: var(--sp-sm) 0;
    color: var(--secondary); font-style: italic;
}
.tau-bubble h1, .tau-bubble h2, .tau-bubble h3, .tau-bubble h4 {
    margin: var(--sp-md) 0 var(--sp-sm); font-weight: 600;
    color: var(--primary);
}
.tau-bubble h1 { font-size: 1.15rem; }
.tau-bubble h2 { font-size: 1.05rem; color: var(--tertiary); }
.tau-bubble h3 { font-size: 0.98rem; }
.tau-bubble h4 { font-size: 0.92rem; }

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 4px; height: 4px; }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: var(--r-full); }
::-webkit-scrollbar-track { background: transparent; }

/* ── Misc ── */
hr { border-color: var(--border) !important; }
a { color: var(--tertiary) !important; }
a:hover { color: var(--tertiary-h) !important; }
</style>
"""

try:
    import markdown as _md_lib
    def _md_to_html(text: str) -> str:
        raw = _md_lib.markdown(text, extensions=['nl2br', 'fenced_code', 'tables'])
        return re.sub(r'<(script|iframe|object|embed)[^>]*>.*?</\1>', '', raw, flags=re.DOTALL | re.IGNORECASE)
except ImportError:
    def _md_to_html(text: str) -> str:
        t = html.escape(text)
        t = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', t, flags=re.DOTALL)
        t = re.sub(r'`([^`]+)`', r'<code>\1</code>', t)
        t = t.replace('\n\n', '</p><p>').replace('\n', '<br>')
        return f'<p>{t}</p>' if t else ''


def render_html_message(role: str, content: str, ts: str = '') -> None:
    is_user = role == 'user'
    cls = 'user' if is_user else 'agent'
    avatar_text = '你' if is_user else 'G'
    meta = ts if is_user else f'Tau · {ts}'
    # user input is plain-escaped; agent output goes through markdown pipeline
    content_html = html.escape(content) if is_user else _md_to_html(content)
    st.markdown(f"""
<div class="tau-msg {cls}">
  <div class="tau-avatar {cls}">{avatar_text}</div>
  <div class="tau-msg-wrap">
    <span class="tau-msg-meta">{meta}</span>
    <div class="tau-bubble {cls}">{content_html}</div>
  </div>
</div>""", unsafe_allow_html=True)


def render_html_sys_message(text: str) -> None:
    st.markdown(
        f'<div class="tau-sys-msg"><span>{html.escape(text)}</span></div>',
        unsafe_allow_html=True
    )


def render_typing_html() -> None:
    st.markdown("""
<div class="tau-msg">
  <div class="tau-avatar agent">G</div>
  <div class="tau-msg-wrap">
    <span class="tau-msg-meta">Tau · 正在输入…</span>
    <div class="tau-bubble agent">
      <div class="tau-typing"><span></span><span></span><span></span></div>
    </div>
  </div>
</div>""", unsafe_allow_html=True)


@st.cache_resource
def init():
    agent = Tau()
    if agent.llmclient is None:
        st.error("⚠️ 未配置任何可用的 LLM 接口，请在 .tau/taukey.py 中添加 sider_cookie 或 oai_apikey+oai_apibase 等信息后重启（可运行 `tau configure` 配置）。")
        st.stop()
    else:
        threading.Thread(target=agent.run, daemon=True).start()
    return agent


agent = init()

def init_session_state():
    for key, value in {
        'agent_name': 'Tau', 'streaming': False, 'stopping': False,
        'display_queue': None, 'partial_response': '', 'reply_ts': '',
        'current_prompt': '', 'selected_llm_idx': agent.llm_no,
        'autonomous_enabled': False, 'messages': [],
        'session_start_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'token_count': 0, 'conversation_rounds': 0,
    }.items():
        st.session_state.setdefault(key, value)

init_session_state()

st.markdown(DESIGN_CSS, unsafe_allow_html=True)

render_html_sys_message(f"{st.session_state.session_start_time} · 会话已建立")
render_html_message(
    "assistant",
    "欢迎使用 Tau～ 我已准备就绪，请输入您的指令。",
    ts=st.session_state.session_start_time,
)


@st.fragment
def render_sidebar():
    # Brand block
    st.markdown("""
<div class="tau-brand">
  <div class="tau-brand-logo">Tau</div>
  <span class="tau-brand-name">Tau</span>
</div>""", unsafe_allow_html=True)

    # LLM info
    st.markdown('<div class="tau-sidebar-title">设置</div>', unsafe_allow_html=True)
    llm_options, current_idx = agent.list_llms(), agent.llm_no
    llm_name = agent.get_llm_name() or ''
    st.markdown(f"""
<div class="tau-sidebar-row">
  <label>当前使用的 LLM <span class="tau-badge">ACTIVE</span></label>
  <span class="tau-llm-name" title="{html.escape(llm_name)}">{html.escape(llm_name)}</span>
</div>""", unsafe_allow_html=True)

    # LLM selector
    st.markdown('<div class="tau-sidebar-title">选择链路</div>', unsafe_allow_html=True)
    llm_labels = {idx: f"{idx}: {(name or '').strip()}" for idx, name, _ in llm_options}
    selected_idx = st.selectbox(
        "选择链路",
        [idx for idx, _, _ in llm_options],
        index=next((i for i, (idx, _, _) in enumerate(llm_options) if idx == current_idx), 0),
        format_func=llm_labels.get,
        key="sidebar_llm_select",
        label_visibility="collapsed",
    )
    if selected_idx != current_idx:
        agent.next_llm(selected_idx)
        st.session_state.selected_llm_idx = selected_idx
        st.toast(f"已切换到链路：{llm_labels[selected_idx]}")
        st.rerun()

    # Buttons
    if st.button("↺ 重新注入 System Prompt", key="btn_reinject"):
        agent.llmclient.last_tools = ''
        st.toast("下次将重新注入 System Prompt")
    if st.button("＋ 新建对话", type="primary", key="btn_new_chat"):
        if st.session_state.streaming:
            agent.abort()
        st.session_state.messages = []
        st.session_state.conversation_rounds = 0
        st.session_state.token_count = 0
        st.session_state.session_start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        st.session_state.streaming = False
        st.session_state.stopping = False
        st.session_state.partial_response = ''
        st.session_state.display_queue = None
        st.rerun()

    # Session info — pushed to bottom via flex spacer
    st.markdown('<div class="tau-sidebar-spacer"></div>', unsafe_allow_html=True)
    st.markdown('<div class="tau-sidebar-title">会话信息</div>', unsafe_allow_html=True)
    token_str = f"{st.session_state.token_count:,}" if st.session_state.token_count else "—"
    rounds_str = str(st.session_state.conversation_rounds)
    st.markdown(f"""
<div class="tau-sidebar-row"><label>已用 Token</label><div class="tau-val">{token_str}</div></div>
<div class="tau-sidebar-row"><label>对话轮次</label><div class="tau-val">{rounds_str}</div></div>
""", unsafe_allow_html=True)

with st.sidebar: render_sidebar()


def start_agent_task(prompt):
    st.session_state.display_queue = agent.put_task(prompt, source="user")
    st.session_state.streaming, st.session_state.stopping, st.session_state.partial_response = True, False, ''
    st.session_state.reply_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    st.session_state.current_prompt = prompt


def poll_agent_output(max_items=20):
    q = st.session_state.display_queue
    if q is None:
        st.session_state.streaming = False
        return False
    done = False
    for _ in range(max_items):
        try:
            item = q.get_nowait()
        except queue.Empty:
            break
        if 'next' in item: st.session_state.partial_response = item['next']
        if 'tokens' in item: st.session_state.token_count = int(item['tokens'])
        if 'done' in item:
            st.session_state.partial_response = item['done']
            done = True
            break
    if done: st.session_state.streaming = st.session_state.stopping = False; st.session_state.display_queue = None
    return done


def _get_response_segments(text):
    return [p for p in re.split(r'(?=\*\*LLM Running \(Turn \d+\) \.\.\.\*\*)', text) if p.strip()] or [text]

def finish_streaming_message():
    reply_ts = st.session_state.reply_ts
    st.session_state.messages.extend(
        {"role": "assistant", "content": seg, "time": reply_ts}
        for seg in _get_response_segments(st.session_state.partial_response)
    )
    st.session_state.last_reply_time = int(time.time())
    st.session_state.conversation_rounds += 1
    st.session_state.partial_response = st.session_state.reply_ts = st.session_state.current_prompt = ''

def render_streaming_area():
    if not st.session_state.streaming: return
    with st.container():
        st.markdown('<span class="stop-btn-anchor"></span>', unsafe_allow_html=True)
        if st.button("⏹️ 停止生成", type="primary"):
            agent.abort(); st.session_state.stopping = True
            st.toast("已发送停止信号"); st.rerun()
    reply_ts = st.session_state.reply_ts
    with st.empty().container():
        partial = st.session_state.partial_response
        if partial:
            segments = _get_response_segments(partial)
            for i, seg in enumerate(segments):
                render_html_message("assistant", seg + ("" if i < len(segments) - 1 else "▌"), ts=reply_ts)
        else:
            render_typing_html()
    if poll_agent_output(): finish_streaming_message()
    else: time.sleep(0.2)
    st.rerun()

for msg in st.session_state.messages:
    render_html_message(msg["role"], msg["content"], ts=msg.get("time", ""))
if st.session_state.streaming: render_streaming_area()
if prompt := st.chat_input("请输入指令", disabled=st.session_state.streaming):
    st.session_state.messages.append({"role": "user", "content": prompt, "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
    start_agent_task(prompt)
    st.rerun()

