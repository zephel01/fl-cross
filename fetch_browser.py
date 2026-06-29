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
from core import store, scoring, fetcher
from core import browser_fetch as bf


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--login", action="store_true", help="ログイン用ブラウザを画面ありで開く")
    ap.add_argument("--headful", action="store_true", help="取得を画面ありで実行（デバッグ）")
    ap.add_argument("--keywords", nargs="*", default=["AI", "LLM", "エージェント"])
    args = ap.parse_args()

    if args.login:
        if not bf._is_playwright_available():
            print("Playwright未インストール: pip install playwright && playwright install chromium", file=sys.stderr)
            return 2
        bf.open_for_login()
        print("ログイン情報を保存しました。次回から自動取得で再利用されます。")
        return 0

    cfg = load_config()
    sources = enabled_sources(cfg)
    print("対象サイト:", ", ".join(s.name for s in sources))

    all_new = []

    # 1) httpx で取れるサイト（サーバー描画 / ログイン不要・JS不要）
    httpx_sources = [s for s in sources if not s.login_required and not s.js_required]
    for s in httpx_sources:
        r = fetcher.fetch_source(s, args.keywords)
        print(f"  - {s.name}: {'%d件' % len(r.jobs) if r.ok else r.message} [httpx]")
        all_new += r.jobs

    # 2) ログイン必須 / SPA はブラウザ（Playwright）
    browser_sources = [s for s in sources if s.login_required or s.js_required]
    if browser_sources:
        if not bf._is_playwright_available():
            print("※ ブラウザ取得スキップ（Playwright未インストール）。pip install playwright && playwright install chromium", file=sys.stderr)
        else:
            results = bf.fetch_with_browser(
                browser_sources, args.keywords, headless=not args.headful,
                on_log=lambda m: print("  -", m, "[browser]"),
            )
            for jobs in results.values():
                all_new += jobs

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
