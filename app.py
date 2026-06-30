#!/usr/bin/env python3
"""fl-cross v2 — フリーランス横断 共通ダッシュボード (Streamlit)

起動:
    cd fl-cross
    pip install -r requirements.txt
    streamlit run app.py

構成:
  - サイドバー: よく使う操作（キーワード/並び替え/ステータス/マッチ率/リモート/稼働日数/取得）
  - タブ: 案件一覧 / 絞り込み詳細 / 設定 / 取り込み / 使い方
"""
from __future__ import annotations

import json
import subprocess
import sys as _sys
from datetime import date
from pathlib import Path

import streamlit as st

from core.config import (
    load_config, save_agent_toggles, save_exclude_providers, save_ng_words,
    save_scoring_weights, save_llm_config,
)
from core.sources import SOURCES, SOURCE_BY_KEY, all_toggles, enabled_sources
from core import store, scoring, fetcher, ingest, dedup
from core import browser_fetch as _bf
from core.providers import job_provider
from core.areas import (
    REGIONS, REMOTE_FULL, REMOTE_PARTIAL, REMOTE_GENERIC, ONSITE, UNKNOWN,
    job_remote_level, job_prefecture,
)
from core.workdays import days_set, days_label

st.set_page_config(page_title="fl-cross v2", page_icon="🧭", layout="wide")

if "config" not in st.session_state:
    st.session_state.config = load_config()
config = st.session_state.config
profile = config.get("profile", {})

DEFAULT_KEYWORDS = ["AI", "LLM", "エージェント", "ローカルLLM", "Claude", "vLLM", "Ollama", "インフラ"]
STATUS_OPTIONS = ["未対応", "気になる", "応募済み", "見送り"]
STATUS_BADGE = {"気になる": "⭐", "応募済み": "✅", "見送り": "🚫"}


# ------------------------------------------------------------------
# ヘルパー
# ------------------------------------------------------------------
def _days_ago(iso: str):
    if not iso:
        return None
    try:
        d = date.fromisoformat(iso[:10])
    except ValueError:
        return None
    return (date.today() - d).days


def _job_status(j) -> str:
    return j.status or "未対応"


def _set_status(job_id: str, status: str) -> None:
    allj = store.load_jobs()
    for x in allj:
        if x.id == job_id:
            x.status = "" if status == "未対応" else status
    store.save_jobs(allj)


def _set_notes(job_id: str, notes: str) -> None:
    allj = store.load_jobs()
    for x in allj:
        if x.id == job_id:
            x.notes = notes
    store.save_jobs(allj)


def _monthly(j) -> int:
    if j.rate_monthly_max or j.rate_monthly_min:
        return j.rate_monthly_max or j.rate_monthly_min
    if j.rate_hourly_max or j.rate_hourly_min:
        return (j.rate_hourly_max or j.rate_hourly_min) * 160
    return 0


# ==================================================================
# サイドバー（よく使う操作）
# ==================================================================
st.sidebar.title("🧭 fl-cross v2")
st.sidebar.caption(f"{profile.get('name','')} 向け横断ダッシュボード")

kw_text = st.sidebar.text_input("🔎 検索キーワード(スペース区切り)", value=" ".join(DEFAULT_KEYWORDS))
keywords = [k for k in kw_text.split() if k]

SORT_OPTIONS = [
    "マッチ率（高い順）", "単価（高い順）", "単価（低い順）",
    "新着順（初観測）", "取得元（エージェント）別", "提供元別",
]
sort_opt = st.sidebar.selectbox("並び替え", SORT_OPTIONS, index=0)

status_filter = st.sidebar.multiselect(
    "ステータス絞り込み", STATUS_OPTIONS, default=["未対応", "気になる", "応募済み"],
    help="見送りは既定で非表示。気になるだけ表示などに使えます。",
)
status_set = set(status_filter)

min_score = st.sidebar.slider("マッチ率の下限", 0, 100, 0, 5)

# 月額レンジ(万円)。案件の単価レンジと重なるものを表示。
# 下限0=下限なし、上限PRICE_MAX=上限なし扱い（既定は全件）。
PRICE_MAX = 200
price_lo, price_hi = st.sidebar.slider(
    "月額レンジ(万円)", 0, PRICE_MAX, (0, PRICE_MAX), 5,
    help=f"案件の月額レンジと重なる案件を表示。上限{PRICE_MAX}は『上限なし』扱い。時給のみの案件は×160で月額換算。",
)
include_unknown_rate = st.sidebar.checkbox("単価不明も含める", value=True)

REMOTE_OPTIONS = [REMOTE_FULL, REMOTE_PARTIAL, REMOTE_GENERIC, ONSITE, UNKNOWN]
remote_sel = st.sidebar.multiselect(
    "リモート区分", REMOTE_OPTIONS, default=[REMOTE_FULL, REMOTE_PARTIAL, REMOTE_GENERIC],
)
remote_set = set(remote_sel)

days_sel = st.sidebar.multiselect(
    "稼働日数(週)", [1, 2, 3, 4, 5], default=[], format_func=lambda d: f"週{d}日",
    help="週3を選ぶと『週3〜5』など範囲案件もヒット。未選択なら全件。",
)
days_filter = set(days_sel)
include_unknown_days = st.sidebar.checkbox("稼働日数 不明も含める", value=True) if days_filter else True

hide_stale = st.sidebar.checkbox("受付終了の可能性(古い/消失)を隠す", value=False,
                                 help="最新取得で確認できなかった案件を非表示")
dedup_on = st.sidebar.checkbox("重複を名寄せ（一次ソース優先）", value=False,
                               help="アグリゲーター経由の同一案件をまとめ、直エージェントを代表に。中で各ソースの単価を比較")
_flt_cfg = config.get("filters", {})
exclude_microtasks = st.sidebar.checkbox(
    "🧹 軽作業・総額を除外", value=bool(_flt_cfg.get("exclude_microtasks", True)),
    help="クラウドソーシングの軽作業（検索作業/データ入力/アンケート等）と、"
         "月額でないプロジェクト総額（単価不明のクラウドソーシング案件）を非表示にします。",
)

# --- 取得 ---
st.sidebar.divider()
st.sidebar.subheader("取得")
pw_ok = _bf._is_playwright_available()
if st.sidebar.button("🌐 全サイト自動取得（ブラウザ）", use_container_width=True, disabled=not pw_ok,
                     help="Playwrightで全有効サイト(SPA/ログイン含む)を取得"):
    with st.spinner("ブラウザで全サイト取得中…（30〜90秒）"):
        proc = subprocess.run([_sys.executable, "fetch_browser.py", "--keywords", *keywords],
                              cwd=str(Path(__file__).parent), capture_output=True, text=True, timeout=600)
    st.session_state.browser_log = (proc.stdout or "") + (proc.stderr or "")
    st.rerun()
if not pw_ok:
    st.sidebar.caption("⚠ ブラウザ取得には Playwright が必要:\n`pip install playwright && playwright install chromium`")
else:
    _prof = (Path.home() / ".fl-cross" / "pw-profile").exists()
    st.sidebar.caption("🔑 要ログインサイトは初回のみ:\n`python fetch_browser.py --login`\n"
                       + ("（ログイン: 設定済み）" if _prof else "（未ログイン）"))
if st.sidebar.button("🔄 httpx自動取得（軽量）", use_container_width=True,
                     help="サーバー描画サイトのみ。ブラウザ不要"):
    with st.spinner("取得中..."):
        results = fetcher.fetch_all(config, keywords)
        ta = tu = 0
        msgs = []
        for r in results:
            if r.jobs:
                a, u = store.upsert_jobs(r.jobs)
                ta += a
                tu += u
            msgs.append(f"- {r.source.name}: {r.message}")
        st.session_state.fetch_report = msgs
        st.session_state.fetch_summary = f"新規 {ta} / 更新 {tu}"
    st.rerun()
if "fetch_summary" in st.session_state:
    st.sidebar.success(st.session_state.fetch_summary)
    with st.sidebar.expander("取得ログ"):
        st.markdown("\n".join(st.session_state.get("fetch_report", [])))
        if st.session_state.get("browser_log"):
            st.code(st.session_state["browser_log"][-1500:])

# ==================================================================
# タブ（案件一覧 / 絞り込み詳細 / 設定 / 取り込み / 使い方）
# ==================================================================
st.title("横断案件ダッシュボード")
tab_jobs, tab_summary, tab_filter, tab_settings, tab_import, tab_help = st.tabs(
    ["📋 案件一覧", "📊 サマリー", "🎛 絞り込み詳細", "⚙️ 設定", "📥 取り込み", "ℹ️ 使い方"]
)

# ---------------- 絞り込み詳細（先に評価して変数を確定） ----------------
with tab_filter:
    st.subheader("NGワード（ブラックリスト）")
    st.caption("タイトル・社名・本文・提供元にこれらの語を含む案件を除外します（1行または半角/全角スペース・カンマ区切り）。")
    cur_ng = config.get("filters", {}).get("ng_words", [])
    ng_text = st.text_area("NGワード", value="\n".join(cur_ng), height=120,
                           placeholder="常駐\n派遣\nアダルト\n株式会社○○")
    ng_words = [w.strip() for w in ng_text.replace("、", "\n").replace(",", "\n").split() if w.strip()]
    if set(ng_words) != set(cur_ng):
        config.setdefault("filters", {})["ng_words"] = ng_words
        try:
            save_ng_words(ng_words)
        except Exception as e:  # noqa: BLE001
            st.warning(f"保存に失敗: {e}")

    st.divider()
    st.subheader("提供元で除外（ブラックリスト）")
    st.caption("config.toml に保存され、取得データに依存しません。1行1件、または半角/全角スペース・カンマ区切り。")
    cur_excl = config.get("filters", {}).get("exclude_providers", [])
    excl_text = st.text_area("除外する提供元/社名", value="\n".join(cur_excl), height=110,
                             placeholder="レバテックフリーランス\n株式会社○○")
    new_excl = [w.strip() for w in excl_text.replace("、", "\n").replace(",", "\n").splitlines() if w.strip()]
    if set(new_excl) != set(cur_excl):
        config.setdefault("filters", {})["exclude_providers"] = new_excl
        try:
            save_exclude_providers(new_excl)
        except Exception as e:  # noqa: BLE001
            st.warning(f"保存に失敗: {e}")
    exclude_providers = set(config.get("filters", {}).get("exclude_providers", []))

    # 参考：いまデータに在る提供元（クリックで上の欄にコピペしやすいよう列挙）
    _present = sorted({job_provider(j) for j in store.load_jobs() if job_provider(j)})
    if _present:
        st.caption("データにある提供元（参考）: " + " / ".join(_present))

    st.divider()
    st.subheader("エリア（47都道府県）")
    st.caption("未選択なら全国。地方ごとに選べます。")
    pref_sel: list[str] = []
    rcols = st.columns(2)
    for i, (region, prefs) in enumerate(REGIONS.items()):
        picked = rcols[i % 2].multiselect(region, prefs, default=[], key=f"pref_{region}")
        pref_sel.extend(picked)
    include_unknown_area = st.checkbox("地域不明・記載なしも含める", value=True)
    pref_set = set(pref_sel)

    st.divider()
    min_hourly = st.number_input("最低時給(円, 0=無視)", min_value=0, max_value=30000, value=0, step=500)

# ---------------- 設定（エージェントON/OFF・LLM） ----------------
with tab_settings:
    st.subheader("検索先エージェント（取得元）")
    st.caption("ON のサイトだけ取得・採点・表示されます。")
    toggles = all_toggles(config)
    new_toggles = {}
    scols = st.columns(2)
    for i, s in enumerate(sorted(SOURCES, key=lambda x: x.priority)):
        new_toggles[s.key] = scols[i % 2].checkbox(
            f"{s.name}（{s.type}）", value=toggles[s.key], key=f"tg_{s.key}",
            help=s.note,
        )
    if new_toggles != toggles:
        config.setdefault("agents", {})
        for k, v in new_toggles.items():
            config["agents"].setdefault(k, {})["enabled"] = v
        try:
            save_agent_toggles(new_toggles)
        except Exception as e:  # noqa: BLE001
            st.warning(f"保存に失敗: {e}")

    st.divider()
    st.subheader("LLM設定（深掘り分析）")
    llm_cfg = config.setdefault("llm", {})
    c1, c2 = st.columns(2)
    llm_cfg["provider"] = c1.selectbox("推論方法", ["ollama", "prompt-only"],
                                       index=0 if llm_cfg.get("provider", "ollama") == "ollama" else 1)
    llm_cfg["base_url"] = c2.text_input("Ollama base_url", value=llm_cfg.get("base_url", "http://localhost:11434"))
    llm_cfg["timeout"] = st.number_input("タイムアウト(秒)", 10, 600, int(llm_cfg.get("timeout", 180)), 10)
    if st.button("🔌 接続テスト / モデル一覧"):
        st.session_state.llm_diag = scoring.ollama_diagnose(config)
    diag = st.session_state.get("llm_diag")
    _models = diag["models"] if diag else []
    if diag:
        (st.success if diag["ok"] else st.error)(diag["message"])
    cur_model = llm_cfg.get("model", "qwen2.5:7b")
    if _models:
        llm_cfg["model"] = st.selectbox("モデル", _models,
                                        index=_models.index(cur_model) if cur_model in _models else 0)
    else:
        llm_cfg["model"] = st.text_input("モデル名", value=cur_model)

    # LLM設定を変更したら自動で config.toml に保存（再起動しても戻らない）
    _llm_sig = (llm_cfg.get("provider"), llm_cfg.get("model"),
                llm_cfg.get("base_url"), llm_cfg.get("timeout"))
    if st.session_state.get("_llm_sig") != _llm_sig:
        try:
            save_llm_config(llm_cfg)
            st.session_state["_llm_sig"] = _llm_sig
            st.caption("✅ LLM設定を保存しました")
        except Exception as e:  # noqa: BLE001
            st.warning(f"LLM設定の保存に失敗: {e}")

    st.divider()
    st.subheader("採点の重み")
    st.caption("スライダーを動かすと即再採点されます（合計が100でなくても自動正規化）。")
    sc = config.setdefault("scoring", {})
    wc = st.columns(4)
    sc["weight_keyword"] = wc[0].slider("キーワード", 0, 100, int(sc.get("weight_keyword", 45)), 5)
    sc["weight_rate"] = wc[1].slider("単価", 0, 100, int(sc.get("weight_rate", 25)), 5)
    sc["weight_remote"] = wc[2].slider("リモート", 0, 100, int(sc.get("weight_remote", 15)), 5)
    sc["weight_freshness"] = wc[3].slider("新着", 0, 100, int(sc.get("weight_freshness", 15)), 5)
    if st.button("💾 重みを保存（config.toml）"):
        try:
            save_scoring_weights({k: sc[k] for k in ("weight_keyword", "weight_rate", "weight_remote", "weight_freshness")})
            st.success("保存しました")
        except Exception as e:  # noqa: BLE001
            st.error(f"保存失敗: {e}")

# ---------------- 取り込み ----------------
with tab_import:
    st.subheader("Chrome連携 / 手動で案件を取り込む")
    src_key = st.selectbox("取り込み先エージェント", options=[s.key for s in SOURCES],
                           format_func=lambda k: SOURCE_BY_KEY[k].name)
    st.markdown("**A) JSON(records)で一括取り込み**")
    st.code('[\n  {"title":"...","company":"X社","url":"https://...",\n'
            '   "rate_text":"〜120万円/月","work_style":"フルリモート 週4",\n'
            '   "description":"...","posted_date":"2026-06-25"}\n]', language="json")
    json_text = st.text_area("JSONを貼り付け", height=160, key="json_in")
    if st.button("JSONを取り込む"):
        try:
            data = json.loads(json_text)
            if isinstance(data, dict):
                data = data.get("records") or data.get("jobs") or []
            a, u = ingest.ingest_records(src_key, data, via="chrome")
            st.success(f"取り込み完了: 新規 {a} / 更新 {u}")
        except Exception as e:  # noqa: BLE001
            st.error(f"取り込み失敗: {e}")
    st.divider()
    st.markdown("**B) 手動で1件追加**")
    with st.form("manual_add"):
        m_title = st.text_input("タイトル *")
        m_company = st.text_input("企業")
        m_url = st.text_input("URL")
        m_rate = st.text_input("単価表記 (例: 〜120万円/月, 8000円/時)")
        m_style = st.text_input("働き方 (例: フルリモート 週3)")
        m_date = st.text_input("掲載日 (YYYY-MM-DD)")
        m_desc = st.text_area("案件説明", height=120)
        if st.form_submit_button("追加"):
            if not m_title.strip():
                st.error("タイトルは必須です")
            else:
                a, u = ingest.ingest_single(src_key, title=m_title, company=m_company, url=m_url,
                                            rate_text=m_rate, work_style=m_style, posted_date=m_date,
                                            description=m_desc)
                st.success(f"追加完了: 新規 {a} / 更新 {u}")
    st.divider()
    if st.button("⚠ 全案件データをクリア"):
        store.clear_jobs()
        st.success("jobs.json をクリアしました")

# ---------------- 使い方 ----------------
with tab_help:
    st.markdown(
        """
### 使い方
1. **⚙️設定**タブで取得元エージェントをON/OFF、LLMを設定。
2. サイドバーの **🌐/🔄 取得** で案件を取り込み（要ログインサイトは `python fetch_browser.py --login`）。
3. **📋案件一覧**でマッチ率順に表示。サイドバー＝よく使う絞り込み、**🎛絞り込み詳細**＝NGワード/提供元/エリア/時給。
4. 各案件で **ステータス**（気になる/応募済み/見送り）を設定。見送りは既定で非表示。
5. **🆕** は初観測が新しい案件、**⚠️** は最新取得で確認できず（受付終了の可能性）。
6. 気になる案件は **🤖LLM深掘り分析**（ローカルOllama）。

### マッチ率
ルール採点 = キーワード一致 + 単価 + リモート/働き方 + 新着度（重みは `config.toml [scoring]`）。
        """
    )

# ================= 共有データセット（サマリー/一覧で共用） =================
active = enabled_sources(config)
active_keys = {s.key for s in active}
_base = [j for j in store.load_jobs() if j.source in active_keys]
_base = [j for j in _base if job_provider(j) not in exclude_providers]


def _ng_hit(j) -> bool:
    if not ng_words:
        return False
    hay = " ".join([j.title, j.company, j.description, job_provider(j)]).lower()
    return any(w.lower() in hay for w in ng_words)


ng_removed = sum(1 for j in _base if _ng_hit(j))
_base = [j for j in _base if not _ng_hit(j)]


_MICROTASK_WORDS = _flt_cfg.get("microtask_words") or [
    "検索作業", "検索結果", "データ入力", "データ収集", "アンケート", "単純作業",
    "かんたん作業", "簡単作業", "簡単な作業", "リサーチ", "モニター", "体験談",
    "口コミ", "商品リサーチ", "出品作業", "コピペ",
]


def _is_crowdsourcing(j) -> bool:
    s = SOURCE_BY_KEY.get(j.source)
    return bool(s and getattr(s, "type", "") == "Cloud Sourcing")


def _has_rate(j) -> bool:
    return bool(j.rate_monthly_min or j.rate_monthly_max
               or j.rate_hourly_min or j.rate_hourly_max)


def _noise_hit(j) -> bool:
    """クラウドソーシングの軽作業 or 月額でない総額(単価不明)案件か。"""
    hay = " ".join([j.title or "", j.description or ""])
    if any(w in hay for w in _MICROTASK_WORDS):
        return True
    # 月額・時給が取れない＝総額(一括)や曖昧表記のクラウドソーシング案件を除外
    if _is_crowdsourcing(j) and not _has_rate(j):
        return True
    return False


noise_removed = 0
if exclude_microtasks:
    noise_removed = sum(1 for j in _base if _noise_hit(j))
    _base = [j for j in _base if not _noise_hit(j)]

_base = scoring.score_jobs(_base, config)


def _passes(j):
    if (j.score or 0) < min_score:
        return False
    if status_set and _job_status(j) not in status_set:
        return False
    if hide_stale and j.stale:
        return False
    if remote_set and job_remote_level(j) not in remote_set:
        return False
    if days_filter:
        ds = days_set(j)
        if ds and not (ds & days_filter):
            return False
        if not ds and not include_unknown_days:
            return False
    if pref_set:
        pf = job_prefecture(j)
        if pf and pf not in pref_set:
            return False
        if not pf and not include_unknown_area:
            return False
    if min_hourly:
        hi = j.rate_hourly_max or ((j.rate_monthly_max or 0) // 160)
        if hi and hi < min_hourly:
            return False
    # 月額レンジ(万円)での絞り込み（案件レンジとの重なり判定）
    if price_lo > 0 or price_hi < PRICE_MAX:
        jlo = j.rate_monthly_min or j.rate_monthly_max
        jhi = j.rate_monthly_max or j.rate_monthly_min
        if not jlo and (j.rate_hourly_min or j.rate_hourly_max):
            jlo = (j.rate_hourly_min or j.rate_hourly_max) * 160
            jhi = (j.rate_hourly_max or j.rate_hourly_min) * 160
        if not jlo:
            if not include_unknown_rate:
                return False
        else:
            jlo_m, jhi_m = jlo / 10000, jhi / 10000
            hi_cap = price_hi if price_hi < PRICE_MAX else float("inf")
            if jhi_m < price_lo or jlo_m > hi_cap:
                return False
    return True


shown = [j for j in _base if _passes(j)]

_SORTS = {
    "マッチ率（高い順）": lambda L: L.sort(key=lambda j: (j.score or 0), reverse=True),
    "単価（高い順）": lambda L: L.sort(key=lambda j: (_monthly(j), j.score or 0), reverse=True),
    "単価（低い順）": lambda L: L.sort(key=lambda j: (_monthly(j) if _monthly(j) else 10**12, -(j.score or 0))),
    "新着順（初観測）": lambda L: L.sort(key=lambda j: (j.first_seen or "", j.score or 0), reverse=True),
    "取得元（エージェント）別": lambda L: L.sort(key=lambda j: (j.source_name, -(j.score or 0))),
    "提供元別": lambda L: L.sort(key=lambda j: (job_provider(j) or "～", -(j.score or 0))),
}
_SORTS.get(sort_opt, _SORTS["マッチ率（高い順）"])(shown)


def render_card(j, dup_group=None):
    score = j.score or 0
    color = "🟢" if score >= 70 else ("🟡" if score >= 45 else "⚪")
    prov = job_provider(j)
    rate_disp = j.rate_text or "単価記載なし"
    fage = _days_ago(j.first_seen)
    status_label = {"気になる": "⭐気になる", "応募済み": "✅応募済み", "見送り": "🚫見送り"}.get(j.status, "")
    new_label = "🆕NEW" if (fage is not None and fage <= 2) else ""
    stale_label = "⚠️終了?" if j.stale else ""
    dup_label = f"🔁重複{len(dup_group)}件" if (dup_group and len(dup_group) > 1) else ""
    tags = "　".join(t for t in [new_label, stale_label, dup_label, status_label] if t)
    tags = f"〔{tags}〕 " if tags else ""
    header = (f"{color} **{score:.0f}%**  ｜ 💰 **{rate_disp}**  ｜ {tags}{j.title}  "
              f"｜ _{j.source_name}_ / 提供元:_{prov or '—'}_")
    with st.expander(header):
        fresh = []
        if fage is not None:
            fresh.append(f"初観測: {fage}日前")
        lage = _days_ago(j.last_seen)
        if lage is not None:
            fresh.append(f"最終確認: {lage}日前")
        if j.posted_date:
            fresh.append(f"掲載: {j.posted_date}")
        if j.stale:
            fresh.append("⚠️ 最新取得に無し（受付終了の可能性）")
        if fresh:
            st.caption("　｜　".join(fresh))

        # 重複（名寄せ）：各ソースの単価・提供元を並記（一次ソース優先で代表表示）
        if dup_group and len(dup_group) > 1:
            st.markdown("**🔁 同一とみられる案件（一次ソース優先）**")
            for d in dup_group:
                star = "★" if d is j else "・"
                st.markdown(
                    f"{star} {d.source_name} / 提供元:{job_provider(d) or '—'} ｜ "
                    f"単価:{d.rate_text or '—'} ｜ " + (f"[開く ↗]({d.url})" if d.url else "")
                )
            st.caption("★＝代表（一次ソース）。単価が異なる場合は中抜き等の可能性。")

        meta = []
        if prov:
            meta.append(f"提供元: {prov}")
        if j.rate_text:
            meta.append(f"単価: {j.rate_text}")
        if j.work_style:
            meta.append(f"働き方: {j.work_style}")
        meta.append(f"リモート区分: {job_remote_level(j)}")
        meta.append(f"稼働日数: {days_label(j)}")
        meta.append(f"エリア: {job_prefecture(j) or '不明/記載なし'}")
        st.caption("　｜　".join(meta))

        sc1, sc2 = st.columns([1, 2])
        cur_status = _job_status(j)
        new_status = sc1.selectbox("ステータス", STATUS_OPTIONS,
                                   index=STATUS_OPTIONS.index(cur_status), key=f"st_{j.id}")
        if new_status != cur_status:
            _set_status(j.id, new_status)
            st.rerun()
        note_val = sc2.text_input("メモ", value=j.notes, key=f"note_{j.id}")
        if note_val != j.notes:
            _set_notes(j.id, note_val)

        bd = j.score_breakdown or {}
        if bd:
            bc = st.columns(4)
            bc[0].metric("KW一致", f"{bd.get('keyword',0):.0f}")
            bc[1].metric("単価", f"{bd.get('rate',0):.0f}")
            bc[2].metric("リモート", f"{bd.get('remote',0):.0f}")
            bc[3].metric("新着", f"{bd.get('freshness',0):.0f}")

        if j.skills:
            st.write("スキル: " + ", ".join(j.skills))
        if j.url:
            st.markdown(f"[案件ページを開く ↗]({j.url})")
        if j.description:
            with st.expander("案件説明"):
                st.write(j.description[:4000])

        mdl = config.get("llm", {}).get("model", "")
        if st.button(f"🤖 LLM深掘り分析（{mdl or 'モデル未設定'}）", key=f"llm_{j.id}"):
            with st.spinner(f"{mdl} で分析中..."):
                res = scoring.llm_review(j, config)
            if res["ok"]:
                allj = store.load_jobs()
                for x in allj:
                    if x.id == j.id:
                        x.llm_analysis = res["text"]
                store.save_jobs(allj)
                st.markdown(res["text"])
            else:
                st.error(f"分析できませんでした: {res['error']}")
                st.caption("👇 プロンプトをコピーして他のLLMに投げてもOK")
                st.code(res["prompt"], language="markdown")
        if j.llm_analysis:
            with st.expander("保存済みLLM分析"):
                st.markdown(j.llm_analysis)


# ---------------- サマリー ----------------
with tab_summary:
    if not shown:
        st.info("表示対象がありません。取得・絞り込みを確認してください。")
    else:
        import pandas as pd
        from collections import Counter
        st.subheader(f"サマリー（表示中 {len(shown)}件）")
        g1, g2 = st.columns(2)
        with g1:
            st.caption("取得元（エージェント）別 件数")
            st.bar_chart(pd.Series(Counter(j.source_name for j in shown)).sort_values(ascending=False))
            st.caption("リモート区分")
            st.bar_chart(pd.Series(Counter(job_remote_level(j) for j in shown)))
        with g2:
            st.caption("単価分布（月額・万円）")
            buckets = ["~50", "50-80", "80-100", "100-150", "150~", "不明"]
            bc = Counter()
            for j in shown:
                m = _monthly(j) // 10000
                if m <= 0:
                    bc["不明"] += 1
                elif m < 50:
                    bc["~50"] += 1
                elif m < 80:
                    bc["50-80"] += 1
                elif m < 100:
                    bc["80-100"] += 1
                elif m < 150:
                    bc["100-150"] += 1
                else:
                    bc["150~"] += 1
            st.bar_chart(pd.Series({b: bc.get(b, 0) for b in buckets}))
            st.caption("エリア（都道府県・上位）")
            pref_counts = Counter(job_prefecture(j) or "不明" for j in shown)
            st.bar_chart(pd.Series(dict(pref_counts.most_common(10))))

# ---------------- 案件一覧 ----------------
with tab_jobs:
    st.caption("有効エージェント: " + (", ".join(s.name for s in active) if active else "なし")
               + f"　／　キーワード: {' '.join(keywords) if keywords else '(なし)'}")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("表示件数", len(shown))
    c2.metric("全件(有効サイト)", len(_base))
    c3.metric("平均マッチ率", f"{(sum(j.score or 0 for j in shown)/len(shown)):.0f}" if shown else "—")
    c4.metric("NG除外", ng_removed, delta=(f"-{noise_removed} 軽作業" if noise_removed else None),
              delta_color="off")
    if exclude_providers:
        st.caption("除外中の提供元: " + ", ".join(sorted(exclude_providers)))
    if exclude_microtasks and noise_removed:
        st.caption(f"🧹 軽作業・総額を除外: {noise_removed}件")

    # 一括LLM分析（「気になる」上位N件）
    with st.expander("🤖 気になる案件を一括LLM分析"):
        kininaru = [j for j in shown if j.status == "気になる"]
        st.caption(f"「気になる」: {len(kininaru)}件。上位N件を順に深掘り分析します（詳細ページ取得＋Ollama）。")
        cA, cB = st.columns([1, 1])
        topn = cA.number_input("件数N", 1, 20, min(5, max(1, len(kininaru))))
        enrich = cB.checkbox("詳細ページも取得して精度UP", value=True)
        if st.button("一括分析を実行", disabled=not kininaru):
            targets = kininaru[:int(topn)]
            prog = st.progress(0.0)
            allj = store.load_jobs()
            by_id = {x.id: x for x in allj}
            done = 0
            for i, j in enumerate(targets):
                if enrich and j.url and not j.description:
                    txt = fetcher.fetch_detail_text(j.url)
                    if txt:
                        j.description = (j.description + "\n" + txt)[:4000]
                res = scoring.llm_review(j, config)
                if res["ok"]:
                    if j.id in by_id:
                        by_id[j.id].llm_analysis = res["text"]
                    done += 1
                prog.progress((i + 1) / len(targets))
            store.save_jobs(allj)
            st.success(f"完了: {done}/{len(targets)} 件を分析・保存しました（各案件の『保存済みLLM分析』に表示）")

    if not shown:
        st.info("該当案件がありません。サイドバーで取得するか、絞り込み条件をゆるめてください。")
    elif dedup_on:
        groups = dedup.group_duplicates(shown)
        st.caption(f"名寄せ: {len(shown)}件 → {len(groups)}グループ")
        for g in groups:
            render_card(g[0], dup_group=g)
    else:
        for j in shown:
            render_card(j)
