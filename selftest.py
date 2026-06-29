#!/usr/bin/env python3
"""依存(streamlit)無しで core ロジックを検証するスモークテスト。"""
import json
from pathlib import Path

from core.config import load_config
from core.sources import enabled_sources, all_toggles, SOURCES
from core import normalize as norm, scoring, store

ROOT = Path(__file__).resolve().parent


def main():
    cfg = load_config()
    print("== config ==")
    print("agents toggles:", all_toggles(cfg))
    print("enabled:", [s.name for s in enabled_sources(cfg)])

    # 単価パースの検証
    print("\n== rate parse ==")
    for t in ["〜120万円/月", "9,000円/時 〜 13,000円/時", "60万円/月", "5,000円/時"]:
        print(f"  {t!r} -> {norm.parse_rate(t)}")

    # サンプル取り込み + 採点
    recs = json.loads((ROOT / "data" / "sample_records.json").read_text(encoding="utf-8"))
    jobs = norm.from_records("freelance_hub", recs, fetched_via="manual")
    jobs = scoring.score_jobs(jobs, cfg)
    print("\n== scoring (sample) ==")
    for j in jobs:
        print(f"  {j.score:5.1f}  {j.title[:30]:30}  {j.score_breakdown}")

    # 期待: AIエージェント/ローカルLLM案件が上位、PHP常駐が最下位
    top = jobs[0]
    bottom = jobs[-1]
    assert "PHP" not in top.title, "PHP案件が上位に来てはいけない"
    assert bottom.score < top.score, "採点の順序がおかしい"
    assert "PHP" in bottom.title or "常駐" in bottom.work_style, "常駐レガシーが最下位想定"

    # store 往復（一時ファイルで検証）
    import tempfile
    tmp = Path(tempfile.gettempdir()) / "_flcross_test_jobs.json"
    store.save_jobs(jobs, tmp)
    loaded = store.load_jobs(tmp)
    assert len(loaded) == len(jobs), "store往復で件数不一致"
    tmp.unlink(missing_ok=True)

    print("\nALL OK ✅")


if __name__ == "__main__":
    main()
