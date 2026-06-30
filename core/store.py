"""案件ストア。data/jobs.json に統一スキーマで保存・重複排除する。

堅牢化:
- 保存は原子的書き込み（tmp へ書いて os.replace）で、書き込み中断による破損を防ぐ。
- 保存前に data/backups/ へタイムスタンプ付きバックアップ（直近 KEEP_BACKUPS 件保持）。
- 読み込みで JSON 破損を検知したら最新バックアップから自動復旧する。
  復旧可否は LAST_LOAD_WARNING に記録（UI 表示用）。破損データで上書きしないための保険。
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

from .models import Job

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
JOBS_PATH = DATA_DIR / "jobs.json"
KEEP_BACKUPS = 10


def _backup_dir(p: Path) -> Path:
    """対象 jobs ファイルの隣の backups/ を返す（カスタムパスでも整合）。"""
    return p.parent / "backups"

# 直近の読み込みで復旧/破損が起きた場合のメッセージ（UI 表示用）。正常時は ""。
LAST_LOAD_WARNING = ""


def _parse_jobs(text: str) -> list[Job]:
    raw = json.loads(text)
    if isinstance(raw, dict):
        raw = raw.get("jobs", [])
    return [Job.from_dict(d) for d in raw]


def _backups_newest_first(p: Path) -> list[Path]:
    bdir = _backup_dir(p)
    if not bdir.exists():
        return []
    return sorted(bdir.glob("jobs_*.json"), reverse=True)


def load_jobs(path: Path | None = None) -> list[Job]:
    """案件を読み込む。破損時は最新バックアップから自動復旧する。"""
    global LAST_LOAD_WARNING
    LAST_LOAD_WARNING = ""
    p = path or JOBS_PATH
    if not p.exists():
        return []
    try:
        return _parse_jobs(p.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        # 本体が壊れている → バックアップから復旧を試みる
        for bk in _backups_newest_first(p):
            try:
                jobs = _parse_jobs(bk.read_text(encoding="utf-8"))
                LAST_LOAD_WARNING = (
                    f"jobs.json が破損していたため、バックアップ {bk.name} から復旧しました"
                    f"（元エラー: {type(e).__name__}）。"
                )
                return jobs
            except Exception:  # noqa: BLE001
                continue
        LAST_LOAD_WARNING = (
            f"jobs.json が破損し、復旧可能なバックアップもありませんでした"
            f"（{type(e).__name__}: {e}）。新規取得まで空表示になります。"
        )
        return []


def _write_atomic(p: Path, text: str) -> None:
    """同一ディレクトリに一時ファイルを作って fsync→os.replace で原子的に置換。"""
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=p.name + ".", suffix=".tmp", dir=str(p.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)  # 原子的置換
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def _backup_current(p: Path) -> None:
    """既存の有効な jobs.json をバックアップ。壊れている場合はバックアップしない。"""
    if not p.exists():
        return
    try:
        text = p.read_text(encoding="utf-8")
        json.loads(text)  # 妥当性チェック（壊れていたら退避しない）
    except Exception:  # noqa: BLE001
        return
    bdir = _backup_dir(p)
    bdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    try:
        _write_atomic(bdir / f"jobs_{stamp}.json", text)
    except OSError:
        return
    # 古いバックアップを剪定
    for old in _backups_newest_first(p)[KEEP_BACKUPS:]:
        try:
            old.unlink()
        except OSError:
            pass


def save_jobs(jobs: list[Job], path: Path | None = None) -> None:
    p = path or JOBS_PATH
    _backup_current(p)
    data = [j.to_dict() for j in jobs]
    _write_atomic(p, json.dumps(data, ensure_ascii=False, indent=2))


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
    from datetime import date
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
