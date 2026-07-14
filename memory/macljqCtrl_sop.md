# macljqCtrl SOP — macOS 物理控制层

> 与 `ljqCtrl_sop.md` 同形: 跨平台鼠标/键盘/截图/窗口 API, 但目标 macOS, 底层 Quartz + Cocoa + ApplicationServices (pyobjc)。

## 定位

- 单文件: `memory/macljqCtrl.py` (≈ 9.4KB / 222 行)
- 设计哲学: **不依赖 Accessibility 授权** — 仅用 Quartz CGEvent (鼠标/键盘) 与 CGWindowList (窗枚举/截图)。AX API
...[Truncated]...
 可在 claude code 外调用 ✅
- 截图 失败 是普遍预期: 沙箱/锁屏下 CGWindowListCreateImage 返回 None → 调 adb/虚拟屏等替代

## 与 ljqCtrl_sop.md 关系

- 共用 API 命名与签名, 上层逻辑可"双写" mac/win (try import macljqCtrl except ImportError: import ljqCtrl)
- mac 版无 pyautogui, 也不试图模拟. win 版 (ljqCtrl.py) 用 pyautogui/pynput

## 后续 TODO

- e2e 联调: 解锁屏幕后用 screenshot + vision_api + macljqCtrl.Click 完整闭环
- CropToScreen 加 out_path 参数 (目前返回 None)
- 添加 CGEventTap 监听 (用于自定义宏录制)