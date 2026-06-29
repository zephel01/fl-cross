"""案件ストア。data/jobs.json に統一スキーマで保存・重複排除する。"""
from __future__ import annotations

import json
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


def upsert_jobs(new_jobs: list[Job], path: Path | None = None) -> tuple[int, int]:
    """新規案件をマージ。同一IDは新しい内容で更新（採点は再計算前提でクリア）。

    returns (added, updated)
    """
    existing = {j.id: j for j in load_jobs(path)}
    added = updated = 0
    for j in new_jobs:
        if j.id in existing:
            # 採点済みフィールドは保持（再取得で説明が同じなら無駄な再採点を避ける）
            prev = existing[j.id]
            if not j.score and prev.score:
                j.score = prev.score
                j.score_breakdown = prev.score_breakdown
                j.llm_analysis = prev.llm_analysis
            existing[j.id] = j
            updated += 1
        else:
            existing[j.id] = j
            added += 1
    save_jobs(list(existing.values()), path)
    return added, updated


def clear_jobs(path: Path | None = None) -> None:
    save_jobs([], path)
