"""ai_agent.py: 把 ui_detect 和 vision_api 串起来的决策层

# ⚠️ 定位说明
- 本模块只做"决策计算"，不直接执行点击 (ljqCtrl 真实派发留给上层调用方)
- 锁屏/无头环境下也能完整 e2e 验证
- vision_sop 要求"能不用 vision 就不用" -> 本模块优先纯 OCR/UI label 匹配
  -> label 不存在或匹配失败才升级到 vision

# 依赖
- ui_detect.detect (R3)
- vision_api.ask_vision (R4)

# 输出坐标规约: 物理像素坐标, 坐标系同 ljqCtrl (与 detect bbox 一致)
"""

import re
import json
from typing import Any


def _bbox_center(bbox):
    """bbox=[x1,y1,x2,y2] -> (cx,cy) 物理像素中心"""
    x1, y1, x2, y2 = bbox
    return (int((x1 + x2) / 2), int((y1 + y2) / 2))


def _normalize_label(s):
    """宽松匹配: 大小写、空格、引号都不敏感"""
    if s is None:
        return ""
    return re.sub(r"[\s'\"`]+", "", str(s)).lower()


def find_by_label(elements, target_label):
    """根据 label 找元素;返回第一个完全(规范化后)匹配的, 否则 None"""
    norm = _normalize_label(target_label)
    if not norm:
        return None
    for e in elements:
        if _normalize_label(e.get("label")) == norm:
            return e
    # 二级: 子串匹配
    for e in elements:
        lbl = _normalize_label(e.get("label"))
        if lbl and (norm in lbl or lbl in norm):
            return e
    return None


def decide_and_locate(
    intent,
    image_path,
    elements,
    *,
    hint_label=None,
    must_hit_labels=None,
    use_vision_threshold=3,
    conf_threshold=None,
    bbox_verify=False,
    elements_max=20,
    timeout=60,
):
    """决策函数: 在 UI 元素列表里挑出要点击的元素，给出物理坐标。

    Args:
        intent: 用户自然语言意图 ("点 OK")
        image_path: 截图路径 (vision 时用)
        elements: ui_detect 出的 UI 元素列表 (每个含 label/type/bbox/confidence)
        hint_label (str|None): 强 hint，若传入会先尝试这个 label
        must_hit_labels (list[str]|None): 用户白名单，必须命中其一 (路径 1.6)
        use_vision_threshold (int): 候选元素 < 该值时强制走 vision
        conf_threshold (float|None): 最高 conf 低于该值时强制走 vision
        bbox_verify (bool): vision 命中后再做一次 label 校验
        elements_max (int): vision prompt 里塞几个元素 (节流)
        timeout (int): vision 超时秒数

    Returns:
        dict {decision_method, element, center, candidates, fallback_used,
              raw_vision, raw_text, enhanced_path, highest_conf}
    """
    # 路径 1: hint_label 短路 (用户显式给的最高优先级)
    candidates = elements or []
    highest_conf = max((e.get("confidence", 0) for e in candidates), default=0)
    if hint_label:
        hit = find_by_label(candidates, hint_label)
        if hit:
            cx, cy = _bbox_center(hit["bbox"])
            meta = base_meta("label", False, None, None, enhanced="hint_label")
            meta["highest_conf"] = highest_conf
            return {
                **meta,
                "element": hit,
                "center": (cx, cy),
            }

    # 路径 1.6: must_hit_labels 强约束 (用户白名单, 直接命中不依赖子串模糊匹配)
    if must_hit_labels:
        for ml in must_hit_labels:
            hit = find_by_label(candidates, ml)
            if hit:
                cx, cy = _bbox_center(hit["bbox"])
                meta = base_meta("label", False, None, None, enhanced="must_hit")
                meta["highest_conf"] = highest_conf
                return {
                    **meta,
                    "element": hit,
                    "center": (cx, cy),
                }

    # 路径2: 候选足够多且置信度够,先扫一遍
    low_conf = conf_threshold is not None and highest_conf < conf_threshold
    if not low_conf:
        for el in candidates:
            if _normalize_label(intent) in _normalize_label(el.get("label")):
                cx, cy = _bbox_center(el["bbox"])
                meta = base_meta(
                    "label", False, None, None,
                    enhanced="must_hit",
                )
                meta["highest_conf"] = highest_conf
                return {
                    **meta,
                    "element": el,
                    "center": (cx, cy),
                }

    # 路径3: fallback vision (三条件任一: 候选不足 / 候选足够但都没命中 / 低置信度)
    fallback_used = len(candidates) < use_vision_threshold or low_conf
    if not fallback_used:
        return {
            **base_meta(
                "none", False, None,
                "candidates exist but none matched intent; user can refine hint_label",
            ),
        }

    # 走 vision
    from memory import vision_api
    compact = []
    for e in elements[:elements_max]:  # 节流 (参数化)
        compact.append({
            "label": e.get("label"),
            "type": e.get("type"),
            "bbox": e.get("bbox"),
            "conf": round(e.get("confidence", 0), 3),
        })
    prompt = f"""用户意图: {intent}

UI 元素列表(JSON 数组, 已按 conf 排序, 取前 {len(compact)} 个):
{json.dumps(compact, ensure_ascii=False, indent=1)}

请只回一行 JSON, 严格格式(无 markdown fence):
{{"pick_label": "<元素 label 或 null>", "reason": "<一句话中文说明>"}}"""
    raw = vision_api.ask_vision(image_path, prompt=prompt, timeout=timeout)

    # 解析 {"pick_label": "...", "reason": "..."}
    pick_label, reason = _parse_pick(raw)
    if not pick_label:
        return {
            **base_meta(
                "vision", True, raw,
                f"vision returned no pickable: {reason}", enhanced="force_vision",
            ),
        }
    hit = find_by_label(elements, pick_label)
    if hit:
        if bbox_verify and not _bbox_label_match(hit, pick_label):
            return {
                **base_meta(
                    "vision", True, raw,
                    f"vision pick '{pick_label}' failed bbox_verify",
                    enhanced="bbox_reject",
                ),
            }
        cx, cy = _bbox_center(hit["bbox"])
        return {
            **base_meta(
                "vision", True, raw,
                f"vision pick '{pick_label}' ({reason})",
                enhanced="bbox_verified",
            ),
            "element": hit,
            "center": (cx, cy),
        }
    return {
        **base_meta(
            "vision", True, raw,
            f"vision pick '{pick_label}' not found in elements",
            enhanced="force_vision",
        ),
    }


def _bbox_label_match(element, expected_label):
    """bbox_verify: 检查元素 label 与 expected_label 实质一致（归一化比对）"""
    if not element or not expected_label:
        return False
    return _normalize_label(element.get("label", "")) == _normalize_label(expected_label)


def base_meta(method, fallback, raw_vision, raw_text, enhanced=None):
    """统一的返回结构（除 method/element/center/candidates/fallback_used/raw_*/raw_text 外，
    加 highest_conf 与 enhanced_path 字段便于后续审计）"""
    return {
        "decision_method": method,
        "element": None,
        "center": None,
        "candidates": 0,
        "fallback_used": fallback,
        "raw_vision": raw_vision,
        "raw_text": raw_text,
        "enhanced_path": enhanced,
        "highest_conf": 0.0,
    }


def _parse_pick(raw):
    """从 vision 字符串里抠 {'pick_label':..., 'reason':...} 返回 (label, reason)"""
    if not raw:
        return (None, "empty raw")
    raw = raw.strip()
    # 1) 标准 JSON
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return (obj.get("pick_label"), obj.get("reason", ""))
    except Exception:
        pass
    # 2) markdown fence
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.S)
    if m:
        try:
            obj = json.loads(m.group(1))
            if isinstance(obj, dict):
                return (obj.get("pick_label"), obj.get("reason", ""))
        except Exception:
            pass
    # 3) 内嵌
    m = re.search(r"\{[^{}]*\"pick_label\"[^{}]*\}", raw)
    if m:
        try:
            obj = json.loads(m.group(0))
            if isinstance(obj, dict):
                return (obj.get("pick_label"), obj.get("reason", ""))
        except Exception:
            pass
    return (None, "parse failed")
