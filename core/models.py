"""統一 Job スキーマ。全エージェントの案件をこの形に正規化する。"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from typing import Any, Optional


@dataclass
class Job:
    source: str                 # エージェントキー (例: "levtech")
    source_name: str            # 表示名 (例: "レバテックフリーランス")
    title: str
    url: str = ""
    company: str = ""
    description: str = ""
    skills: list[str] = field(default_factory=list)
    # 単価（時給換算。月額しか分からない場合は rate_monthly に入れる）
    rate_hourly_min: Optional[int] = None
    rate_hourly_max: Optional[int] = None
    rate_monthly_min: Optional[int] = None
    rate_monthly_max: Optional[int] = None
    rate_text: str = ""         # 元表記 (例: "〜120万円/月")
    remote: Optional[bool] = None
    remote_type: str = ""       # "フルリモート" | "一部リモート" | "リモート" | "常駐" | "不明"
    days_min: Optional[int] = None  # 稼働日数(週) 下限
    days_max: Optional[int] = None  # 稼働日数(週) 上限
    work_style: str = ""        # 例: "週3〜4日", "フルリモート"
    location: str = ""
    prefecture: str = ""        # 47都道府県のいずれか（検出できた場合）
    posted_date: str = ""       # ISO8601 もしくは元表記
    fetched_via: str = "manual"  # "auto" | "chrome" | "manual"

    # 採点結果（scoring が埋める）
    score: Optional[float] = None
    score_breakdown: dict[str, float] = field(default_factory=dict)
    llm_analysis: str = ""

    @property
    def id(self) -> str:
        """URL優先、無ければ source+title でハッシュ化した安定ID。"""
        basis = self.url.strip() or f"{self.source}:{self.title}"
        return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["id"] = self.id
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Job":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        clean = {k: v for k, v in d.items() if k in known}
        return cls(**clean)
