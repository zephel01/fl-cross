"""提供元(provider)名の正規化。

アグリゲーター(フリーランスHub等)のカードに出る「提供元」は表記揺れや
途中までしか取れていない場合がある(例: "ココナラテック（旧：フリ")。
横断で除外フィルタを効かせるため、代表名に寄せる。
"""
from __future__ import annotations

# (部分一致キーワード, 代表名)
_RULES = [
    ("レバテック", "レバテックフリーランス"),
    ("ココナラテック", "ココナラテック"),
    ("フリエン", "ココナラテック"),
    ("furien", "ココナラテック"),
    ("midworks", "Midworks"),
    ("hipro", "HiPro"),
    ("mijica", "mijicaフリーランス"),
    ("findy", "Findy"),
    ("クラウドワークス", "クラウドワークス"),
    ("crowdworks", "クラウドワークス"),
    ("ランサーズ", "ランサーズ"),
    ("lancers", "ランサーズ"),
    ("フリーランスボード", "フリーランスボード"),
]


def canonical_provider(raw: str) -> str:
    """提供元名を代表名に正規化。未知ならトリムして返す。"""
    if not raw:
        return ""
    low = raw.lower()
    for kw, name in _RULES:
        if kw.lower() in low:
            return name
    return raw.strip()


def job_provider(job, fallback_source_name: str = "") -> str:
    """Job から提供元を決定。company優先、無ければ取得元サイト名。"""
    raw = (getattr(job, "company", "") or "").strip()
    if raw:
        return canonical_provider(raw)
    return canonical_provider(fallback_source_name or getattr(job, "source_name", "")) or getattr(job, "source_name", "")
