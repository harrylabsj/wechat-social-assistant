"""Deterministic perception helpers for Accessibility evidence.

The native AX reader intentionally emits structure, not identity.  This
module contains the small, reviewable heuristics that can be applied to that
structure without turning an ambiguous UI into a claimed conversation fact.
"""

from __future__ import annotations

from dataclasses import replace
import re

from .observations import OCRObservation


_EXPLICIT_LABEL_RE = re.compile(r"^\s*(?P<label>[^:：]{1,32})\s*[:：]\s*$")
_CHINESE_LABEL_RE = re.compile(r"^[\u4e00-\u9fff·]{2,12}$")
_LATIN_LABEL_RE = re.compile(r"^[A-Za-z][A-Za-z ._-]{1,31}$")
_DISALLOWED_LABEL_CHARS = re.compile(r"[，。！？!?；;、()（）\[\]【】<>《》/\\@#$%^&*=+~`|]")
_UI_LABELS = {
    "备注",
    "名称",
    "姓名",
    "内容",
    "主题",
    "标题",
    "来源",
    "通知",
    "提示",
    "状态",
    "时间",
    "日期",
    "消息",
    "系统消息",
    "群公告",
    "聊天记录",
    "联系人",
    "搜索",
    "输入",
    "发送",
    "文件",
    "资料",
    "链接",
    "项目方向",
    "项目内容",
}
_UI_SUFFIXES = ("方向", "内容", "资料", "方案", "项目", "工作", "问题", "消息", "时间", "链接", "文件")


def annotate_accessibility_speakers(
    observations: tuple[OCRObservation, ...],
) -> tuple[OCRObservation, ...]:
    """Attach a low-confidence candidate only for an explicit ``Name:`` label.

    We require both a plausible label and either shared AX parent structure or
    spatial adjacency.  A bare preceding short line is deliberately ignored;
    that case is already handled by the existing group-chat heuristic at the
    storage boundary and should not be upgraded merely because AX was used.
    The candidate is attached to the following message observation, where it
    describes the message rather than the label itself.
    """

    if len(observations) < 2:
        return observations
    annotated = list(observations)
    for index, label_observation in enumerate(observations[:-1]):
        if label_observation.speaker_candidate:
            continue
        candidate = explicit_speaker_label(label_observation.text)
        if candidate is None:
            continue
        target = observations[index + 1]
        if target.speaker_candidate or not _is_message_candidate(target.text):
            continue
        if not _is_adjacent(label_observation, target):
            continue
        confidence_values = [0.65]
        if label_observation.confidence is not None:
            confidence_values.append(label_observation.confidence)
        if target.confidence is not None:
            confidence_values.append(target.confidence)
        annotated[index + 1] = replace(
            target,
            speaker_candidate=candidate,
            speaker_confidence=min(confidence_values),
        )
    return tuple(annotated)


def explicit_speaker_label(text: str) -> str | None:
    """Return a plausible explicit speaker label, otherwise ``None``."""

    match = _EXPLICIT_LABEL_RE.match(text or "")
    if not match:
        return None
    label = match.group("label").strip()
    if not _is_plausible_label(label):
        return None
    return label


def _is_plausible_label(label: str) -> bool:
    if not label or label in _UI_LABELS or any(label.endswith(suffix) for suffix in _UI_SUFFIXES):
        return False
    if _DISALLOWED_LABEL_CHARS.search(label):
        return False
    return bool(_CHINESE_LABEL_RE.fullmatch(label) or _LATIN_LABEL_RE.fullmatch(label))


def _is_message_candidate(text: str) -> bool:
    cleaned = " ".join((text or "").split())
    if len(cleaned) < 2:
        return False
    # Another explicit label is a second header, not a message to attribute.
    return explicit_speaker_label(cleaned) is None


def _is_adjacent(label: OCRObservation, message: OCRObservation) -> bool:
    same_parent = bool(label.parent_path and message.parent_path and label.parent_path == message.parent_path)
    if label.bbox is None or message.bbox is None:
        return same_parent

    lx, ly, lw, lh = label.bbox
    mx, my, mw, mh = message.bbox
    horizontal_overlap = min(lx + lw, mx + mw) - max(lx, mx)
    centers_close = abs((lx + lw / 2) - (mx + mw / 2)) <= max(lw, mw, 0.02) * 2.5
    # Vision/AX coordinates use a lower-left origin.  A speaker label is
    # normally above its message, but a compact same-row layout is also common.
    above = ly + max(lh, 0.01) >= my + mh - max(lh, mh) * 0.75
    vertical_gap = abs((ly + lh / 2) - (my + mh / 2))
    near = vertical_gap <= max(lh, mh, 0.02) * 3.0
    return (same_parent or centers_close or horizontal_overlap > 0) and above and near
