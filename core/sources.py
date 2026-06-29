"""エージェント（検索先）定義レジストリ。

各エージェントは:
  - key          : config の [agents.<key>] と対応
  - name         : 表示名
  - type         : Aggregator / Agent / Cloud Sourcing
  - priority     : 優先度
  - base_url     : トップ
  - search_url   : 検索ベースURL
  - build_search : キーワード -> 検索URL を作る関数
  - login_required : ログイン必須か（自動取得が困難 → Chrome連携推奨）
  - parser_key   : fetcher 側のパーサ識別子（None なら汎用パーサ）
  - note         : メモ
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional
from urllib.parse import quote_plus


@dataclass
class Source:
    key: str
    name: str
    type: str
    priority: int
    base_url: str
    search_url: str
    build_search: Callable[[list[str]], str]
    login_required: bool = False
    js_required: bool = False     # 完全クライアント描画でhttpx自動取得が不可（要Chrome）
    parser_key: Optional[str] = None
    note: str = ""


def _plus(keywords: list[str]) -> str:
    return "+".join(quote_plus(k) for k in keywords)


def _space(keywords: list[str]) -> str:
    return quote_plus(" ".join(keywords))


SOURCES: list[Source] = [
    Source(
        key="freelance_hub",
        name="フリーランスHub",
        type="Aggregator",
        priority=1,
        base_url="https://freelance-hub.jp/",
        search_url="https://freelance-hub.jp/project/search/",
        build_search=lambda kw: f"https://freelance-hub.jp/project/search/?keyword={_plus(kw)}",
        login_required=False,
        js_required=True,
        parser_key="freelance_hub",
        note="36万件超のアグリゲーター。Vue製SPAでhttpx自動取得は不可→Chrome連携で取得",
    ),
    Source(
        key="levtech",
        name="レバテックフリーランス",
        type="Agent",
        priority=2,
        base_url="https://freelance.levtech.jp/",
        search_url="https://freelance.levtech.jp/project/search/",
        build_search=lambda kw: f"https://freelance.levtech.jp/project/search/?keyword={_space(kw)}",
        login_required=True,
        parser_key="levtech",
        note="高単価・非公開案件多数。ログイン/JS描画が多く Chrome連携推奨",
    ),
    Source(
        key="findy",
        name="Findy Freelance",
        type="Agent",
        priority=3,
        base_url="https://freelance.findy-code.io/",
        search_url="https://freelance.findy-code.io/works",
        build_search=lambda kw: f"https://freelance.findy-code.io/works?keyword={_space(kw)}",
        login_required=True,
        js_required=True,
        parser_key="findy",
        note="ログイン後 /works で検索。ハイスキル・スタートアップ・高リモート率。要ログイン＋ブラウザ取得",
    ),
    Source(
        key="crowdworks_tech",
        name="クラウドワークス テック",
        type="Cloud Sourcing",
        priority=4,
        base_url="https://tech.crowdworks.jp/",
        search_url="https://tech.crowdworks.jp/job_offers",
        build_search=lambda kw: f"https://tech.crowdworks.jp/job_offers?keywords={_space(kw)}",
        login_required=False,
        js_required=True,
        parser_key="crowdworks_tech",
        note="IT特化公開案件。完全CSR(Vite)でhttpx自動取得は不可→Chrome連携で取得",
    ),
    Source(
        key="lancers",
        name="ランサーズ",
        type="Cloud Sourcing",
        priority=5,
        base_url="https://www.lancers.jp/",
        search_url="https://www.lancers.jp/work/search",
        build_search=lambda kw: f"https://www.lancers.jp/work/search?keyword={_space(kw)}",
        login_required=False,
        parser_key="lancers",
        note="日本最大級クラウドソーシング。実績作り向け",
    ),
    Source(
        key="freelance_board",
        name="フリーランスボード",
        type="Aggregator",
        priority=6,
        base_url="https://freelance-board.com/",
        search_url="https://freelance-board.com/",
        build_search=lambda kw: f"https://freelance-board.com/?keyword={_space(kw)}",
        login_required=False,
        parser_key="freelance_board",
        note="50万件超アグリゲーター。AIマッチ機能あり。SPA寄り",
    ),
    Source(
        key="itpropartners",
        name="ITプロパートナーズ",
        type="Agent",
        priority=7,
        base_url="https://itpropartners.com/",
        search_url="https://itpropartners.com/job",
        build_search=lambda kw: "https://itpropartners.com/job",
        login_required=False,
        js_required=False,
        parser_key="itpropartners",
        note="週2-3日・リモート豊富、エンド直請け高単価寄り。公開案件をhttpx取得可",
    ),
    Source(
        key="midworks",
        name="Midworks",
        type="Agent",
        priority=8,
        base_url="https://mid-works.com/",
        search_url="https://mid-works.com/projects",
        build_search=lambda kw: "https://mid-works.com/projects",
        login_required=False,
        js_required=False,
        parser_key="midworks",
        note="言語・職種別の公開案件検索。報酬保証など福利厚生。httpx取得可",
    ),
    Source(
        key="techfree",
        name="テクフリ",
        type="Agent",
        priority=9,
        base_url="https://freelance.techcareer.jp/",
        search_url="https://freelance.techcareer.jp/projects/search/",
        build_search=lambda kw: "https://freelance.techcareer.jp/projects/search/",
        login_required=False,
        js_required=False,
        parser_key="techfree",
        note="高単価・マージン率公開。エンジニアファースト。httpx取得可",
    ),
    Source(
        key="pebank",
        name="PE-BANK",
        type="Agent",
        priority=10,
        base_url="https://pe-bank.jp/",
        search_url="https://pe-bank.jp/project/",
        build_search=lambda kw: "https://pe-bank.jp/project/",
        login_required=False,
        js_required=False,
        parser_key="pebank",
        note="案件検索可。地方案件も強い。httpx取得可（月額は万円表記）",
    ),
    Source(
        key="flexy",
        name="FLEXY（サーキュレーション）",
        type="Agent",
        priority=11,
        base_url="https://pro.circu.info/",
        search_url="https://pro.circu.info/mypage/projects/search",
        build_search=lambda kw: "https://pro.circu.info/mypage/projects/search",
        login_required=True,
        js_required=True,
        parser_key="flexy",
        note="ハイスキル・高単価。ログイン必須(pro.circu.info)。要ログイン＋ブラウザ取得",
    ),
]

SOURCE_BY_KEY = {s.key: s for s in SOURCES}


def enabled_sources(config: dict) -> list[Source]:
    """config の [agents] トグルで有効なエージェントだけを優先度順に返す。"""
    agents = config.get("agents", {}) or {}
    out = []
    for s in SOURCES:
        a = agents.get(s.key, {})
        if a.get("enabled", True):
            out.append(s)
    return sorted(out, key=lambda s: s.priority)


def all_toggles(config: dict) -> dict[str, bool]:
    agents = config.get("agents", {}) or {}
    return {s.key: bool(agents.get(s.key, {}).get("enabled", True)) for s in SOURCES}
