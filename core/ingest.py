"""Chrome連携 / 手動インポート用の取り込みヘルパー。

Claude in Chrome でページから抜き出した案件、または手動で用意した
JSON / CSV / 貼り付けテキストを統一スキーマに正規化して store に追加する。

JSON形式（推奨, records）:
[
  {"title": "...", "company": "...", "url": "...", "rate_text": "〜120万円/月",
   "work_style": "フルリモート 週3", "description": "...", "posted_date": "2026-06-25"},
  ...
]
"""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any

from .models import Job
from . import normalize as norm
from . import store


def ingest_records(source_key: str, records: list[dict[str, Any]], via: str = "chrome") -> tuple[int, int]:
    jobs = norm.from_records(source_key, records, fetched_via=via)
    return store.upsert_jobs(jobs)


def ingest_json_file(source_key: str, path: str | Path, via: str = "chrome") -> tuple[int, int]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("records") or data.get("jobs") or []
    return ingest_records(source_key, data, via=via)


def ingest_csv_text(source_key: str, text: str, via: str = "manual") -> tuple[int, int]:
    reader = csv.DictReader(io.StringIO(text))
    records = [dict(r) for r in reader]
    return ingest_records(source_key, records, via=via)


def ingest_single(source_key: str, *, title: str, **kw) -> tuple[int, int]:
    job = norm.normalize(source_key, title=title, fetched_via="manual", **kw)
    return store.upsert_jobs([job])
