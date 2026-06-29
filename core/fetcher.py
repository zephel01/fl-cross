"""自動取得（ベストエフォート）。

公開検索ページを httpx + BeautifulSoup で取得し、案件カードを抽出する。
- ログイン必須/SPA のサイトは取得が困難なため、空 or 部分結果を返し、
  UI 側で「Chrome連携 or 手動インポート推奨」と案内する。
- サイト構造は変わりうる。汎用パーサ(_generic_parse)で見出し+リンクを拾い、
  サイト別パーサがあればそちらを優先する。

⚠ 各サイトの利用規約・robots.txt を尊重すること。過度なアクセスは避ける。
"""
from __future__ import annotations

import time
from typing import Any, Callable, Optional

from .models import Job
from .sources import Source, enabled_sources, SOURCE_BY_KEY
from . import normalize as norm

UA = "Mozilla/5.0 (compatible; fl-cross/2.0; +personal-job-search)"
TIMEOUT = 25.0


class FetchResult:
    def __init__(self, source: Source):
        self.source = source
        self.jobs: list[Job] = []
        self.ok = False
        self.message = ""

    def __repr__(self) -> str:
        return f"<FetchResult {self.source.key} ok={self.ok} n={len(self.jobs)} {self.message}>"


def _get_html(url: str) -> Optional[str]:
    try:
        import httpx
    except ImportError:
        return None
    try:
        with httpx.Client(timeout=TIMEOUT, follow_redirects=True, headers={"User-Agent": UA}) as c:
            r = c.get(url)
            r.raise_for_status()
            return r.text
    except Exception:  # noqa: BLE001
        return None


def _soup(html: str):
    from bs4 import BeautifulSoup
    return BeautifulSoup(html, "html.parser")


# ------------------------------------------------------------------
# 汎用パーサ：案件リンクらしき <a> を見出しとして拾う
# ------------------------------------------------------------------

def _generic_parse(html: str, source: Source, limit: int = 40) -> list[dict[str, Any]]:
    import re as _re
    soup = _soup(html)
    records: list[dict[str, Any]] = []
    seen = set()
    # ナビ/フッター等の定型リンクを除外するための語
    NAV = ("ログイン", "会員登録", "サイトマップ", "お問い合わせ", "利用規約",
           "プライバシー", "よくある質問", "求人案件", "運営会社", "検索条件",
           "保存した", "メニュー", "スカウト", "一覧", "トップ")
    # 案件詳細っぽい URL（一覧/検索/スキル絞り込み等は除外）
    DETAIL = _re.compile(r"/(project|projects|job_offer|jobs|work|works)?/?(detail/)?\d{4,}")
    YEN = _re.compile(r"[\d,]+\s*(万円|円)")
    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True)
        href = a["href"]
        if not text or len(text) < 10:
            continue
        if any(n in text for n in NAV):
            continue
        if not DETAIL.search(href):
            continue
        # 近傍カードに単価表記があるものだけ採用（ナビ・関連リンク除去）
        card = a
        card_text = ""
        for _ in range(7):
            if card.parent is None:
                break
            card = card.parent
            card_text = card.get_text(" ", strip=True)
            if YEN.search(card_text):
                break
        if not YEN.search(card_text):
            continue
        full = source.base_url.rstrip("/") + href if href.startswith("/") else href
        if full in seen:
            continue
        seen.add(full)
        rate_m = YEN.search(card_text)
        records.append({
            "title": text[:120],
            "url": full,
            "rate_text": rate_m.group(0) if rate_m else "",
            "description": card_text[:300],
        })
        if len(records) >= limit:
            break
    return records


# サイト別パーサ（必要に応じ精緻化。未実装は汎用にフォールバック）
PARSERS: dict[str, Callable[[str, Source], list[dict[str, Any]]]] = {}


def fetch_source(source: Source, keywords: list[str]) -> FetchResult:
    res = FetchResult(source)
    if source.login_required:
        res.message = "ログイン必須。自動取得不可 → Chrome連携で取得してください"
        return res
    if source.js_required:
        res.message = "JS描画(SPA/CSR)のため自動取得不可 → Chrome連携で取得してください"
        return res
    url = source.build_search(keywords)
    html = _get_html(url)
    if not html:
        res.message = "取得失敗（ネットワーク/規約/SPAの可能性）。Chrome連携 or 手動推奨"
        return res
    parser = PARSERS.get(source.parser_key or "", None)
    try:
        records = parser(html, source) if parser else _generic_parse(html, source)
    except Exception as e:  # noqa: BLE001
        res.message = f"パース失敗: {e}"
        return res
    res.jobs = norm.from_records(source.key, records, fetched_via="auto")
    res.ok = len(res.jobs) > 0
    res.message = f"{len(res.jobs)}件取得" if res.ok else "0件（構造変化の可能性。Chrome連携推奨）"
    return res


def fetch_all(config: dict, keywords: list[str], polite_delay: float = 1.0) -> list[FetchResult]:
    results = []
    for s in enabled_sources(config):
        results.append(fetch_source(s, keywords))
        time.sleep(polite_delay)
    return results
