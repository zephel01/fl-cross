"""クロスサイト名寄せ（重複統合）。

アグリゲーター経由で同一案件が複数サイトに重複するため、タイトル類似でグルーピングし、
「一次ソース（直エージェント＞クラウドソーシング＞アグリゲーター）」を代表に据える。
単価が中抜き等で異なることがあるので、重複は消さずグループ内に各ソースを残す。
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

# 取得元の一次ソース度（小さいほど一次＝代表に選ばれやすい）
SOURCE_TIER = {
    "levtech": 1, "findy": 1, "itpropartners": 1, "midworks": 1, "techfree": 1, "pebank": 1,
    "crowdworks_tech": 2, "lancers": 2,
    "freelance_hub": 3, "freelance_board": 3,  # アグリゲーター（再掲）
}

_SUFFIXES = ["の案件・求人", "の案件", "求人", "業務委託フリーランス", "業務委託", "フリーランス", "案件"]


def norm_title(t: str) -> str:
    t = t or ""
    t = re.sub(r"[【】\[\]（）()／/・,、。\.\s　|｜]", "", t)
    for suf in _SUFFIXES:
        t = t.replace(suf, "")
    return t.lower()


def _similar(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def tier(job) -> int:
    return SOURCE_TIER.get(getattr(job, "source", ""), 5)


def group_duplicates(jobs: list, threshold: float = 0.86) -> list[list]:
    """類似タイトルでグルーピング。各グループは (tier, -score) 昇順で代表が先頭。

    返り値: グループのリスト。グループ表示の並びは代表のスコア降順。
    """
    norms = [norm_title(j.title) for j in jobs]
    used = [False] * len(jobs)
    groups: list[list] = []
    for i in range(len(jobs)):
        if used[i]:
            continue
        group = [jobs[i]]
        used[i] = True
        for k in range(i + 1, len(jobs)):
            if used[k]:
                continue
            # タイトル類似のみで判定（保守的に高しきい値）
            if _similar(norms[i], norms[k]) >= threshold:
                group.append(jobs[k])
                used[k] = True
        group.sort(key=lambda j: (tier(j), -(getattr(j, "score", 0) or 0)))
        groups.append(group)
    groups.sort(key=lambda g: (g[0].score or 0), reverse=True)
    return groups
