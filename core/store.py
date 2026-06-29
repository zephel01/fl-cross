"""案件ストア。data/jobs.json に統一スキーマで保存・重複排除する。"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .models import Job

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
JOBS_PATH = DATA_DIR / "jobs.json"


def load_jobs(path: Path | None = None) -> list[Job]:
    p = path or JOBS_PATH
    if not p.exists():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []
    return [Job.from_dict(d) for d in raw]


def save_jobs(jobs: list[Job], path: Path | None = None) -> None:
    p = path or JOBS_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    data = [j.to_dict() for j in jobs]
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def upsert_jobs(new_jobs: list[Job], path: Path | None = None,
                mark_missing_stale: bool = False) -> tuple[int, int]:
    """新規案件をマージ。同一IDは更新しつつ、ユーザー項目・観測日を保持する。

    - first_seen: 新規時に今日。既存は維持。
    - last_seen : 今回取得分に今日をセット。
    - status / notes / llm_analysis / score は既存値を引き継ぐ。
    - mark_missing_stale=True: 今回の取得に現れなかった既存案件を stale=True に。
      （同じ取得元の案件のみ対象＝部分取得で誤判定しないよう、呼び出し側で全体取得時のみ使用）

    returns (added, updated)
    """
    today = date.today().isoformat()
    existing = {j.id: j for j in load_jobs(path)}
    seen_ids = set()
    added = updated = 0
    for j in new_jobs:
        seen_ids.add(j.id)
        prev = existing.get(j.id)
        if prev:
            # ユーザー/観測/採点の引き継ぎ
            j.first_seen = prev.first_seen or today
            j.last_seen = today
            j.stale = False
            j.status = prev.status
            j.notes = prev.notes
            if not j.score and prev.score:
                j.score = prev.score
                j.score_breakdown = prev.score_breakdown
            if not j.llm_analysis and prev.llm_analysis:
                j.llm_analysis = prev.llm_analysis
            existing[j.id] = j
            updated += 1
        else:
            j.first_seen = today
            j.last_seen = today
            existing[j.id] = j
            added += 1
    if mark_missing_stale:
        sources = {j.source for j in new_jobs}
        for jid, j in existing.items():
            if jid not in seen_ids and j.source in sources:
                j.stale = True
    save_jobs(list(existing.values()), path)
    return added, updated


def clear_jobs(path: Path | None = None) -> None:
    save_jobs([], path)
