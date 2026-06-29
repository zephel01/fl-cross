"""稼働日数(週何日)の判定。

"週3", "週3〜4日", "週4-5日", "週3日～", "週5(40時間)" などから
最小・最大の稼働日数を推定する。
"""
from __future__ import annotations

import re
from typing import Optional

# 全角→半角の数字・記号も拾う
_SEP = r"〜～~\-－"  # 半角/全角チルダ・ハイフン各種
_RANGE = re.compile(rf"週\s*([1-7１-７])\s*日?\s*[{_SEP}]\s*([1-7１-７])")
_SINGLE = re.compile(r"週\s*([1-7１-７])")
_PLUS = re.compile(rf"週\s*([1-7１-７])\s*日?\s*(?:[{_SEP}＋\+]|以上)")  # 週3日～/週3以上 → 下限のみ

_Z2H = str.maketrans("１２３４５６７", "1234567")


def parse_days(text: str) -> tuple[Optional[int], Optional[int]]:
    """テキストから (最小日数, 最大日数) を推定。無ければ (None, None)。"""
    if not text:
        return (None, None)
    t = text.translate(_Z2H)
    m = _RANGE.search(t)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return (min(a, b), max(a, b))
    # 「週3日～」のように下限のみ
    mp = _PLUS.search(t)
    if mp:
        return (int(mp.group(1)), 5)
    ms = _SINGLE.search(t)
    if ms:
        d = int(ms.group(1))
        return (d, d)
    return (None, None)


def job_days_range(job) -> tuple[Optional[int], Optional[int]]:
    lo = getattr(job, "days_min", None)
    hi = getattr(job, "days_max", None)
    if lo or hi:
        return (lo, hi)
    text = " ".join([
        getattr(job, "work_style", "") or "",
        getattr(job, "description", "") or "",
        getattr(job, "title", "") or "",
    ])
    return parse_days(text)


def days_label(job) -> str:
    lo, hi = job_days_range(job)
    if lo and hi:
        return f"週{lo}" if lo == hi else f"週{lo}〜{hi}"
    if lo:
        return f"週{lo}〜"
    return "不明"


def days_set(job) -> set[int]:
    """この案件が取りうる稼働日数の集合（フィルタ照合用）。"""
    lo, hi = job_days_range(job)
    if lo and hi:
        return set(range(lo, hi + 1))
    if lo:
        return set(range(lo, 6))
    return set()
