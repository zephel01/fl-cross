#!/usr/bin/env python3
"""ブラウザ自動取得CLI（Playwright）。

  python fetch_browser.py --login          # 初回: 画面ありでログイン用ブラウザを開く
  python fetch_browser.py                   # 有効サイトを全部取得 → jobs.json に保存
  python fetch_browser.py --headful         # 画面ありで取得（デバッグ用）
  python fetch_browser.py --keywords AI LLM エージェント
"""
from __future__ import annotations

import argparse
import sys

from core.config import load_config
from core.sources import enabled_sources
from core import store, scoring
from core import browser_fetch as bf


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--login", action="store_true", help="ログイン用ブラウザを画面ありで開く")
    ap.add_argument("--headful", action="store_true", help="取得を画面ありで実行（デバッグ）")
    ap.add_argument("--keywords", nargs="*", default=["AI", "LLM", "エージェント"])
    args = ap.parse_args()

    if not bf._is_playwright_available():
        print("Playwright が未インストールです。\n  pip install playwright\n  playwright install chromium", file=sys.stderr)
        return 2

    if args.login:
        bf.open_for_login()
        print("ログイン情報を保存しました。次回から自動取得で再利用されます。")
        return 0

    cfg = load_config()
    sources = enabled_sources(cfg)
    print("対象サイト:", ", ".join(s.name for s in sources))
    results = bf.fetch_with_browser(
        sources, args.keywords, headless=not args.headful, on_log=lambda m: print("  -", m)
    )

    all_new = [j for jobs in results.values() for j in jobs]
    if not all_new:
        print("取得0件。ログインが必要な場合は `python fetch_browser.py --login` を実行してください。")
        return 0
    added, updated = store.upsert_jobs(all_new)
    allj = scoring.score_jobs(store.load_jobs(), cfg)
    store.save_jobs(allj)
    print(f"\n保存完了: 新規 {added} / 更新 {updated} / 合計 {len(allj)} 件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
