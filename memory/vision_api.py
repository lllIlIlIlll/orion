import base64, requests, sys, os
from io import BytesIO
from pathlib import Path

# ============ 用户配置区（从 template 拷贝后只需改这里）============
# TAU自举提示：
# taukey.py配置变量名不固定；默认值失败时，枚举候选变量名，并用最小vision请求实验探测哪组配置可用。
# 只打印变量名/字段名/model/apibase域名路径/HTTP状态码/错误类型，禁止打印完整dict和apikey/token。
# 常见格式：
#   xxx_config = {"apibase": "https://.../v1", "apikey": "...", "model": "...", "proxy": None}
# 不同中转的 apibase/endpoint 可能不同，按实际状态码和响应结构修正。
CLAUDE_CONFIG_KEY = 'native_claude_config_0'   # taukey.py 中 Claude 配置的变量名 (M3@api.minimaxi.com/anthropic)
OPENAI_CONFIG_KEY = 'native_claude_config_1'   # fallback: Kimi@api.kimi.com/coding (兼容 anthropic-style)
MODELSCOPE_API_KEY = ''                        # 直接填你的 ModelScope token (保底)
DEFAULT_BACKEND = 'claude'                     # 默认后端: 'claude' / 'openai' / 'modelscope'
# =================================================================

MODELSCOPE_API_BASE = 'https://api-inference.modelscope.cn'
MODELSCOPE_MODEL = 'Qwen/Qwen3-VL-235B-A22B-Instruct'

_DIR = os.path.dirname(os.path.abspath(__file__))
for _p in [os.path.join(_DIR, '..'), os.path.join(_DIR, '../..')]:
    if _p not in sys.path: sys.path.insert(0, _p)

def ask_vision(image_input, prompt="详细描述这张图片的内容", timeout=60, max_pixels=1440000, backend=DEFAULT_BACKEND):
    try:
        b64 = _prepare_image(image_input, max_pixels)
    except Exception as e:
        return f"Error: 图片处理失败 - {type(e).__name__}: {e}"
    try:
        if backend == 'claude':
            return _call_claude(b64, prompt, timeout)
        elif backend == 'openai':
            mk = _load_config()
            cfg = getattr(mk, OPENAI_CONFIG_KEY)
            return _call_openai_compat(
                b64, prompt, timeout,
                apibase=cfg['apibase'], apikey=cfg['apikey'], model=cfg['model'], proxy=cfg.get('proxy')
            )
        elif backend == 'modelscope':
            return _call_openai_compat(
                b64, prompt, timeout,
                apibase=MODELSCOPE_API_BASE, apikey=MODELSCOPE_API_KEY, model=MODELSCOPE_MODEL, proxy=None
            )
        else: return f"Error: 未知backend '{backend}'，可选: claude, openai, modelscope"
    except requests.exceptions.Timeout:
        return f"Error: 请求超时 (>{timeout}s)"
    except requests.exceptions.RequestException as e:
        return f"Error: API请求失败 - {type(e).__name__}: {e}"
    except (KeyError, ValueError) as e:
        return f"Error: 响应解析失败 - {e}"

# ===================== 以下为内部实现 =====================

def _prepare_image(image_input, max_pixels=1440000):
    """加载+缩放+base64编码，返回b64字符串"""
    from PIL import Image
    if isinstance(image_input, Image.Image):
        img = image_input
    elif isinstance(image_input, (str, Path)):
        img = Image.open(image_input)
    else:
        raise TypeError(f"image_input 必须是文件路径或PIL Image，实际: {type(image_input).__name__}")
    w, h = img.size
    if w * h > max_pixels:
        scale = (max_pixels / (w * h)) ** 0.5
        new_w, new_h = int(w * scale), int(h * scale)
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        print(f"  📐 缩放: {w}×{h} → {new_w}×{new_h}")
    if img.mode in ('RGBA', 'LA', 'P'):
        rgb = Image.new('RGB', img.size, (255, 255, 255))
        rgb.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
        img = rgb
    buf = BytesIO()
    img.save(buf, format='JPEG', quality=80, optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    print(f"  📦 Base64: {len(buf.getvalue())/1024:.1f}KB")
    return b64

def _load_config():
    import taukey
    return taukey

def _call_claude(b64, prompt, timeout, max_tokens=1024):
    mk = _load_config()
    cfg = getattr(mk, CLAUDE_CONFIG_KEY)
    resp = requests.post(
        cfg['apibase'] + '/v1/messages',   # endpoint按中转实际情况改：有的apibase已含/v1，或路径不同
        json={'model': cfg['model'], 'max_tokens': max_tokens, 'messages': [{
            'role': 'user',
            'content': [
                {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/jpeg', 'data': b64}},
                {'type': 'text', 'text': prompt}
            ]
        }]},
        headers={'x-api-key': cfg['apikey'], 'anthropic-version': '2023-06-01', 'content-type': 'application/json'},
        timeout=timeout
    )
    resp.raise_for_status()
    return resp.json()['content'][0]['text']

def _call_openai_compat(b64, prompt, timeout, *, apibase, apikey, model, proxy=None):
    proxies = {'https': proxy, 'http': proxy} if proxy else None
    resp = requests.post(
        apibase.rstrip('/') + '/v1/chat/completions',   # endpoint按中转实际情况改：有的apibase已含/v1，或路径不同
        json={'model': model, 'messages': [{
            'role': 'user',
            'content': [
                {'type': 'text', 'text': prompt},
                {'type': 'image_url', 'image_url': {'url': f'data:image/jpeg;base64,{b64}'}}
            ]
        }]},
        headers={'Authorization': f"Bearer {apikey}", 'Content-Type': 'application/json'},
        proxies=proxies, timeout=timeout
    )
    resp.raise_for_status()
    return resp.json()['choices'][0]['message']['content']

# ===================== R28: 多后端路由/重试/降级/cost 估算 =====================

# 默认 auto 路由时的优先级与 cost (USD / 1K tokens, 大致, 用于排序)
# 数字越小越便宜
_BACKEND_COST_HINT = {
    'modelscope': 0.0,    # ModelScope 部分模型免费
    'openai':     0.01,   # GPT-4o-mini 级别
    'claude':     0.015,  # Claude Haiku 级别
}

# auto 模式时，preferred chain (按 cost 升序; 同 cost 时顺序在前优先)
DEFAULT_BACKEND_CHAIN = ['modelscope', 'openai', 'claude']

# 重试参数
RETRY_BACKOFF = [0, 2, 5]   # 第一次立即, 之后等 2s, 5s


def _estimate_cost(backend, b64_size, prompt_len):
    """粗略估算一次请求 cost ($USD). 仅用于排序/统计,非计费."""
    b = backend.lower()
    base = _BACKEND_COST_HINT.get(b, 0.01)
    # 假定平均输出 200 tokens, 输入 = image_kb + prompt_kb
    in_tok = (b64_size / 1024) * 0.3 + (prompt_len / 4)
    out_tok = 200
    cost = (in_tok + out_tok) / 1000 * base
    return round(cost, 6)


def _call_with_retry(call_fn, timeout):
    """带退避重试的 HTTP 调用. 捕获 Timeout/RequestException; 返回最终响应对象.

    call_fn(timeout) -> requests.Response
    raise_for_status() 由调用方负责.
    """
    import requests as _req
    last_exc = None
    for delay in RETRY_BACKOFF:
        if delay:
            import time; time.sleep(delay)
        try:
            resp = call_fn(timeout)
            # 5xx 当作可重试
            if getattr(resp, 'status_code', 200) >= 500:
                last_exc = _req.exceptions.HTTPError(f"Server error {resp.status_code}")
                continue
            return resp
        except (_req.exceptions.Timeout, _req.exceptions.ConnectionError, _req.exceptions.HTTPError) as e:
            last_exc = e
            continue
    raise last_exc  # type: ignore[misc]


class BackendClient:
    """轻量基类: 描述能力与代价, 子类实现 call(b64, prompt, timeout)."""
    name = 'base'

    def __init__(self, name):
        self.name = name

    def call(self, b64, prompt, timeout):
        raise NotImplementedError

    def cost_hint(self):
        return _BACKEND_COST_HINT.get(self.name, 0.01)


class ClaudeBackend(BackendClient):
    def __init__(self):
        super().__init__('claude')

    def call(self, b64, prompt, timeout, max_tokens=1024):
        mk = _load_config()
        cfg = getattr(mk, CLAUDE_CONFIG_KEY)
        def _do(t):
            return requests.post(
                cfg['apibase'] + '/v1/messages',
                json={'model': cfg['model'], 'max_tokens': max_tokens, 'messages': [{
                    'role': 'user',
                    'content': [
                        {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/jpeg', 'data': b64}},
                        {'type': 'text', 'text': prompt}
                    ]
                }]},
                headers={'x-api-key': cfg['apikey'], 'anthropic-version': '2023-06-01', 'content-type': 'application/json'},
                timeout=t
            )
        resp = _call_with_retry(_do, timeout)
        resp.raise_for_status()
        return resp.json()['content'][0]['text']


class OpenAICompatBackend(BackendClient):
    def __init__(self, name, apibase, apikey, model, proxy=None):
        super().__init__(name)
        self.apibase = apibase
        self.apikey = apikey
        self.model = model
        self.proxy = proxy

    def call(self, b64, prompt, timeout):
        proxies = {'https': self.proxy, 'http': self.proxy} if self.proxy else None
        def _do(t):
            return requests.post(
                self.apibase.rstrip('/') + '/v1/chat/completions',
                json={'model': self.model, 'messages': [{
                    'role': 'user',
                    'content': [
                        {'type': 'text', 'text': prompt},
                        {'type': 'image_url', 'image_url': {'url': f'data:image/jpeg;base64,{b64}'}}
                    ]
                }]},
                headers={'Authorization': f"Bearer {self.apikey}", 'Content-Type': 'application/json'},
                proxies=proxies, timeout=t
            )
        resp = _call_with_retry(_do, timeout)
        resp.raise_for_status()
        return resp.json()['choices'][0]['message']['content']


def _make_openai_backend():
    mk = _load_config()
    cfg = getattr(mk, OPENAI_CONFIG_KEY)
    return OpenAICompatBackend('openai', cfg['apibase'], cfg['apikey'], cfg['model'], cfg.get('proxy'))


def _make_modelscope_backend():
    return OpenAICompatBackend('modelscope', MODELSCOPE_API_BASE, MODELSCOPE_API_KEY, MODELSCOPE_MODEL, None)


_BACKEND_FACTORIES = {
    'claude':     ClaudeBackend,
    'openai':     _make_openai_backend,
    'modelscope': _make_modelscope_backend,
}


def _get_backend(name):
    """根据名字返回一个 BackendClient 实例 (工厂模式)."""
    factory = _BACKEND_FACTORIES.get(name)
    if not factory:
        raise ValueError(f"未知 backend '{name}'，可选: {list(_BACKEND_FACTORIES)}")
    return factory() if isinstance(factory, type) else factory()


def _try_with_fallback(b64, prompt, timeout, chain):
    """依次尝试 chain 内 backend, 失败回退. 返回 (text, backend_used, attempts).

    raises 最后一次的非 HttpException, 若都因临时错误失败, 抛 RuntimeError 汇总.
    """
    import requests as _req
    attempts = []
    last_exc = None
    for name in chain:
        try:
            client = _get_backend(name)
            text = client.call(b64, prompt, timeout)
            attempts.append({'backend': name, 'ok': True})
            return text, name, attempts
        except (_req.exceptions.RequestException, KeyError, ValueError) as e:
            attempts.append({'backend': name, 'ok': False, 'err': type(e).__name__})
            last_exc = e
            continue
    raise RuntimeError(f"所有 backend 均失败 chain={chain} attempts={attempts}; last={last_exc}")


# 兼容入口: backend='auto' 使用 cost 排序自动选, 失败链式降级
def ask_vision_smart(image_input, prompt="详细描述这张图片的内容", timeout=60, max_pixels=1440000,
                      prefer=None, fallbacks=None):
    """R28 智能入口: prefer 指定首选, fallbacks 为降级链 (默认 DEFAULT_BACKEND_CHAIN)."""
    try:
        b64 = _prepare_image(image_input, max_pixels)
    except Exception as e:
        return f"Error: 图片处理失败 - {type(e).__name__}: {e}"
    b64_size = len(b64)
    # 构造链: [prefer] + fallbacks (去重保序)
    if prefer is None:
        prefer = DEFAULT_BACKEND_CHAIN[0]
    chain = [prefer]
    fb = fallbacks or DEFAULT_BACKEND_CHAIN
    for n in fb:
        if n not in chain:
            chain.append(n)
    cost = _estimate_cost(prefer, b64_size, len(prompt))
    try:
        text, used, attempts = _try_with_fallback(b64, prompt, timeout, chain)
        print(f"  💰 估算 cost ${cost} | 实际使用 backend={used} | chain 尝试 {attempts}")
        return text
    except RuntimeError as e:
        return f"Error: {e}"


if __name__ == '__main__':
    pass