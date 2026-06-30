"""生テキスト/辞書 → 統一 Job スキーマへの正規化ヘルパー。

自動取得・Chrome連携・手動インポートのいずれも最終的にここを通す。
単価・リモート可否・スキルなどを日本語表記から推定する。
"""
from __future__ import annotations

import re
from typing import Any, Optional

from .models import Job
from .sources import SOURCE_BY_KEY

# 単価表記の正規表現
_MAN = r"(\d{2,4})\s*万"          # 例: 120万
_YEN_H = r"([\d,]{3,7})\s*円?\s*/?\s*(?:時|h|hour|時間)"  # 例: 8,000円/時
_NUM = r"([\d,]+)"


def _to_int(s: str) -> Optional[int]:
    try:
        return int(s.replace(",", ""))
    except (ValueError, AttributeError):
        return None


def parse_rate(text: str, bare_yen_monthly: bool = True) -> dict[str, Any]:
    """単価表記から hourly/monthly レンジを推定して返す。

    bare_yen_monthly:
      6〜7桁の「素の円」(例: "1,210,000 円") を月額とみなすか。
      エージェントの単価表記は月額が基本なので既定True。
      クラウドソーシング(ランサーズ等)はプロジェクト総額(一括)の場合が多いため
      False を渡し、「月」表記がある時だけ月額採用＝総額の取り込みを防ぐ。
    """
    out: dict[str, Any] = {"rate_text": text.strip() if text else ""}
    if not text:
        return out
    t = text.replace(",", "")

    # 時給
    hour_nums = re.findall(r"(\d{3,6})\s*円?\s*/?\s*(?:時|h|hour|時間)", t)
    if hour_nums:
        nums = sorted(int(n) for n in hour_nums)
        out["rate_hourly_min"] = nums[0]
        out["rate_hourly_max"] = nums[-1]
        return out

    # 月額（万円）レンジ: 単位を後ろに共有する "60〜90万", "月額 46 ～ 50 万円" 等
    # （下限側に万が無いケースを取りこぼさない）
    man_range = re.search(r"(\d{2,4})\s*万?\s*[〜～~\-―ー－]\s*(\d{2,4})\s*万", t)
    if man_range:
        lo, hi = sorted((int(man_range.group(1)), int(man_range.group(2))))
        out["rate_monthly_min"] = lo * 10000
        out["rate_monthly_max"] = hi * 10000
        return out

    # 月額（万円）
    man_nums = re.findall(r"(\d{2,4})\s*万", t)
    if man_nums:
        nums = sorted(int(n) * 10000 for n in man_nums)
        out["rate_monthly_min"] = nums[0]
        out["rate_monthly_max"] = nums[-1]
        return out

    # 月額（円, 6-7桁）。エージェントは月額が基本なので採用。
    # クラウドソーシング(bare_yen_monthly=False)では「月」表記がある時のみ採用し、
    # プロジェクト総額(一括)を月額として取り込まないようにする。
    if bare_yen_monthly or "月" in t:
        big = re.findall(r"(\d{6,7})", t)
        if big:
            nums = sorted(int(n) for n in big)
            out["rate_monthly_min"] = nums[0]
            out["rate_monthly_max"] = nums[-1]
    return out


REMOTE_WORDS = ["フルリモート", "リモート", "remote", "在宅"]


def detect_remote(text: str) -> Optional[bool]:
    if not text:
        return None
    low = text.lower()
    if any(w.lower() in low for w in REMOTE_WORDS):
        return True
    if "常駐" in text or "出社" in text:
        return False
    return None


_SKILL_HINTS = [
    "Python", "Go", "Rust", "TypeScript", "React", "AWS", "GCP", "Azure",
    "Docker", "Kubernetes", "LLM", "RAG", "LangChain", "vLLM", "Ollama",
    "PyTorch", "MLOps", "Claude", "OpenAI", "生成AI", "エージェント", "MCP",
]


def extract_skills(text: str) -> list[str]:
    if not text:
        return []
    found = []
    for s in _SKILL_HINTS:
        if s.lower() in text.lower():
            found.append(s)
    return found


def normalize(
    source_key: str,
    *,
    title: str,
    description: str = "",
    url: str = "",
    company: str = "",
    rate_text: str = "",
    work_style: str = "",
    location: str = "",
    posted_date: str = "",
    fetched_via: str = "manual",
    extra: Optional[dict[str, Any]] = None,
) -> Job:
    from .areas import remote_level, detect_prefecture
    from .workdays import parse_days
    src = SOURCE_BY_KEY.get(source_key)
    source_name = src.name if src else source_key
    # クラウドソーシング(ランサーズ等)は素の円が総額の場合が多いので月額断定しない。
    is_crowdsourcing = bool(src and getattr(src, "type", "") == "Cloud Sourcing")
    rate = parse_rate(rate_text or "", bare_yen_monthly=not is_crowdsourcing)
    body = " ".join([title, description, work_style])
    area_body = " ".join([location, work_style, description, title])
    d_lo, d_hi = parse_days(body)
    job = Job(
        source=source_key,
        source_name=source_name,
        title=title.strip(),
        url=url.strip(),
        company=company.strip(),
        description=description.strip(),
        skills=extract_skills(body),
        rate_text=rate.get("rate_text", ""),
        rate_hourly_min=rate.get("rate_hourly_min"),
        rate_hourly_max=rate.get("rate_hourly_max"),
        rate_monthly_min=rate.get("rate_monthly_min"),
        rate_monthly_max=rate.get("rate_monthly_max"),
        remote=detect_remote(body),
        remote_type=remote_level(body),
        days_min=d_lo,
        days_max=d_hi,
        work_style=work_style.strip(),
        location=location.strip(),
        prefecture=detect_prefecture(area_body),
        posted_date=posted_date.strip(),
        fetched_via=fetched_via,
    )
    if extra:
        for k, v in extra.items():
            if hasattr(job, k) and v not in (None, ""):
                setattr(job, k, v)
    return job


def from_records(source_key: str, records: list[dict[str, Any]], fetched_via: str = "auto") -> list[Job]:
    """パーサが返した辞書リストを Job リストへ。"""
    jobs = []
    for r in records:
        if not r.get("title"):
            continue
        jobs.append(
            normalize(
                source_key,
                title=r.get("title", ""),
                description=r.get("description", ""),
                url=r.get("url", ""),
                company=r.get("company", ""),
                rate_text=r.get("rate_text", "") or r.get("rate", ""),
                work_style=r.get("work_style", ""),
                location=r.get("location", ""),
                posted_date=r.get("posted_date", ""),
                fetched_via=fetched_via,
            )
        )
    return jobs
