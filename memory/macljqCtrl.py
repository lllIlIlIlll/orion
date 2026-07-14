"""
macljqCtrl — macOS 物理控制层 (Quartz 优先 + Cocoa NSWorkspace 兜底)
目标: 提供 ljqCtrl_sop.md 中描述的核心 API 在 macOS 上的对应实现

物理层抽象:
  - 鼠标/键盘: pyobjc Quartz (CGEvent) — 无需 Accessibility 授权 ✅
  - 截屏: Quartz CGWindowListCreateImage — ⚠️ 沙箱禁, 失败回 nil (graceful fallback)
  - 窗口枚举: CGWindowListCopyWindowInfo — ✅ 可读
  - 窗口激活: NSWorkspace runningApplications + AppKit NSApplicationActivate — ✅ 可发

API (与 ljqCtrl.py 同形):
  ListWindows(filter_visible=True, owner=None) -> [{id,name,owner,bounds,pid}]
  FindWindow(name=None, owner=None) -> {id,...} | None
  ActivateApp(name) -> bool
  Click(x, y) -> bool
  MoveTo(x, y) -> bool
  Press(key, modifiers=None) -> bool
  Screenshot(path=None) -> str|None  (沙箱下多返回 None)
  CropToScreen(img_path, bbox) -> str|None
  IsAXTrusted() -> bool

沙箱行为:
  - 鼠标/键盘事件: 可 post (实际是否生效取决于系统)
  - 截屏: 返回 None, 不抛异常
  - 窗口激活: NSRunningApplication.activateWithOptions_, 可能 success 但视觉无变化
"""
from __future__ import annotations
import os
import time
import subprocess
from typing import Optional, List, Dict, Any, Tuple

# ── Quartz ──
import Quartz
from Quartz import (
    CGEventCreateMouseEvent, CGEventCreateKeyboardEvent, CGEventPost,
    kCGHIDEventTap,
    kCGEventMouseMoved, kCGEventLeftMouseDown, kCGEventLeftMouseUp, kCGEventRightMouseDown, kCGEventRightMouseUp,
    CGEventSourceCreate, kCGEventSourceStateHIDSystemState,
    CGWindowListCopyWindowInfo, CGWindowListCreateImage,
    kCGWindowListOptionOnScreenOnly, kCGNullWindowID, kCGWindowImageDefault,
    CGMainDisplayID, CGDisplayBounds, CGEventGetLocation,
)
# ── Cocoa / NSWorkspace ──
import AppKit
from AppKit import NSWorkspace, NSRunningApplication, NSApplicationActivateAllWindows

# ── 常量 ──
_kVK = {  # 部分常用键码
    'a': 0x00, 's': 0x01, 'd': 0x02, 'f': 0x03, 'h': 0x04, 'g': 0x05,
    'z': 0x06, 'x': 0x07, 'c': 0x08, 'v': 0x09, 'b': 0x0B, 'q': 0x0C,
    'w': 0x0D, 'e': 0x0E, 'r': 0x0F, 'y': 0x10, 't': 0x11, 'o': 0x1F,
    'u': 0x20, 'i': 0x22, 'p': 0x23, 'l': 0x25, 'j': 0x26, 'k': 0x28,
    'n': 0x2D, 'm': 0x2E,
    '1': 0x12, '2': 0x13, '3': 0x14, '4': 0x15, '5': 0x16, '6': 0x17,
    '7': 0x18, '8': 0x19, '9': 0x1A, '0': 0x1B,
    'return': 0x24, 'enter': 0x24, 'tab': 0x30, 'space': 0x31,
    'delete': 0x33, 'backspace': 0x33, 'escape': 0x35, 'esc': 0x35,
    'shift': 0x38, 'capslock': 0x39, 'command': 0x37, 'cmd': 0x37,
    'option': 0x3A, 'alt': 0x3A, 'control': 0x3B, 'ctrl': 0x3B,
    'left': 0x7B, 'right': 0x7C, 'down': 0x7D, 'up': 0x7E,
    'f1': 0x7A, 'f2': 0x78, 'f3': 0x63, 'f4': 0x76,
}


# ───────────── 窗口枚举 ─────────────
def ListWindows(filter_visible: bool = True, owner: Optional[str] = None) -> List[Dict[str, Any]]:
    """枚举当前屏幕上的窗口列表 (读 Quartz, 无需授权)"""
    opts = kCGWindowListOptionOnScreenOnly if filter_visible else 0
    raw = CGWindowListCopyWindowInfo(opts, kCGNullWindowID)
    out = []
    for w in raw:
        d = {
            'id': w.get('kCGWindowNumber'),
            'name': w.get('kCGWindowName', ''),
            'owner': w.get('kCGWindowOwnerName', ''),
            'pid': w.get('kCGWindowOwnerPID'),
            'bounds': dict(w.get('kCGWindowBounds', {})),
            'layer': w.get('kCGWindowLayer'),
            'on_screen': w.get('kCGWindowIsOnscreen', False),
        }
        if owner and owner.lower() not in (d['owner'] or '').lower():
            continue
        out.append(d)
    return out


def FindWindow(name: Optional[str] = None, owner: Optional[str] = None) -> Optional[Dict[str, Any]]:
    for w in ListWindows(filter_visible=True, owner=owner):
        if name is None or (name.lower() in (w.get('name') or '').lower()):
            return w
    return None


# ───────────── 应用激活 ─────────────
def ActivateApp(name: str) -> bool:
    """通过 NSWorkspace 激活 app (可能视觉无变化, 但 API 调用成功)"""
    ws = NSWorkspace.sharedWorkspace()
    apps = ws.runningApplications()
    target = None
    for app in apps:
        if app.localizedName() == name or app.bundleIdentifier() == name:
            target = app
            break
    if target is None:
        return False
    ok = target.activateWithOptions_(NSApplicationActivateAllWindows)
    return bool(ok)


# ───────────── 鼠标 ─────────────
def _post(event):
    CGEventPost(kCGHIDEventTap, event)


def MoveTo(x: float, y: float) -> bool:
    e = CGEventCreateMouseEvent(None, kCGEventMouseMoved, (x, y), 0)
    _post(e)
    return True


def Click(x: float, y: float, button: str = 'left') -> bool:
    if button == 'left':
        down_evt, up_evt = kCGEventLeftMouseDown, kCGEventLeftMouseUp
    elif button == 'right':
        down_evt, up_evt = kCGEventRightMouseDown, kCGEventRightMouseUp
    else:
        raise ValueError(f'unsupported button {button}')
    down = CGEventCreateMouseEvent(None, down_evt, (x, y), 0)
    up = CGEventCreateMouseEvent(None, up_evt, (x, y), 0)
    _post(down); time.sleep(0.02); _post(up)
    return True


# ───────────── 键盘 ─────────────
def Press(key: str, modifiers: Optional[List[str]] = None) -> bool:
    """按 key (可带 modifiers 如 ['command','shift']), 例: Press('c', ['command'])"""
    src = CGEventSourceCreate(kCGEventSourceStateHIDSystemState)
    k = key.lower()
    code = _kVK.get(k)
    if code is None:
        raise ValueError(f'unknown key {key}, add to _kVK')
    # modifier down
    mods = modifiers or []
    for m in mods:
        mc = _kVK.get(m.lower())
        if mc is None: continue
        _post(CGEventCreateKeyboardEvent(src, mc, True))
    _post(CGEventCreateKeyboardEvent(src, code, True))
    time.sleep(0.02)
    _post(CGEventCreateKeyboardEvent(src, code, False))
    for m in reversed(mods):
        mc = _kVK.get(m.lower())
        if mc is None: continue
        _post(CGEventCreateKeyboardEvent(src, mc, False))
    return True


# ───────────── 截屏 ─────────────
def Screenshot(path: Optional[str] = None) -> Optional[str]:
    """全屏截图, 失败(沙箱禁)返回 None 而非抛异常"""
    try:
        img = CGWindowListCreateImage(
            CGDisplayBounds(CGMainDisplayID()),
            kCGWindowListOptionOnScreenOnly,
            kCGNullWindowID,
            kCGWindowImageDefault,
        )
        if img is None:
            return None
        if path is None:
            path = os.path.expanduser('~/Desktop/macljqCtrl_screenshot.png')
        from Quartz import CGImageDestinationCreateWithURL, CGImageDestinationAddImage, kUTTypePNG
        from CoreFoundation import CFURLCreateWithFileSystemPath, kCFURLPOSIXPathStyle, kCFAllocatorDefault
        url = CFURLCreateWithFileSystemPath(kCFAllocatorDefault, path, kCFURLPOSIXPathStyle, False)
        dest = CGImageDestinationCreateWithURL(url, 'public.png', 1, None)
        CGImageDestinationAddImage(dest, img, None)
        ok = Quartz.CGImageDestinationFinalize(dest) if hasattr(Quartz, 'CGImageDestinationFinalize') else True
        return path if ok else None
    except Exception:
        return None


def CropToScreen(img_path: str, bbox: Tuple[int, int, int, int]) -> Optional[str]:
    """对已截图片按 bbox 剪裁; img_path 不存在则返回 None"""
    try:
        from Quartz import CGImageSourceCreateWithURL, CGImageSourceCreateImageAtIndex, CGImageCreateWithImageInRect
        from CoreFoundation import CFURLCreateWithFileSystemPath, kCFURLPOSIXPathStyle, kCFAllocatorDefault
        url = CFURLCreateWithFileSystemPath(kCFAllocatorDefault, img_path, kCFURLPOSIXPathStyle, False)
        src = CGImageSourceCreateWithURL(url, None)
        if src is None: return None
        img = CGImageSourceCreateImageAtIndex(src, 0, None)
        if img is None: return None
        rect = ((bbox[0], bbox[1]), (bbox[2], bbox[3]))
        crop = CGImageCreateWithImageInRect(img, rect)
        if crop is None: return None
        return path if path else None
    except Exception:
        return None


# ───────────── AX 状态 ─────────────
def IsAXTrusted() -> bool:
    try:
        import ApplicationServices as AS
        return bool(AS.AXIsProcessTrusted())
    except Exception:
        return False


# ───────────── 自检 ─────────────
def _selftest():
    print('=== macljqCtrl 自检 ===')
    print('AX trusted:', IsAXTrusted())
    wins = ListWindows(filter_visible=True)
    print(f'visible windows: {len(wins)}')
    if wins:
        print(f'sample: {wins[0]["owner"]} / "{wins[0]["name"]}" @ {wins[0]["bounds"]}')
    print('Click(500,500) ->', Click(500, 500))
    print('MoveTo(100,100) ->', MoveTo(100, 100))
    print('Press(a) ->', Press('a'))
    print('Press(c, [command]) ->', Press('c', ['command']))
    p = Screenshot('/tmp/macljqCtrl_selftest.png')
    print('Screenshot ->', p)
    print('ActivateApp("Finder") ->', ActivateApp('Finder'))


if __name__ == '__main__':
    _selftest()