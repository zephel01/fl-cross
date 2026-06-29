#!/usr/bin/env python3
"""fl-cross v2 — フリーランス横断 共通ダッシュボード (Streamlit)

起動:
    cd fl-cross
    pip install -r requirements.txt
    streamlit run app.py

機能:
  - サイドバー: エージェント(検索先)の有効/無効トグル + フィルタ
  - 横断取得(自動 / Chrome連携JSON / 手動) -> 統一スキーマ
  - ハイブリッド・マッチ率(ルール) で降順表示
  - 各案件を Ollama で深掘り分析
"""
from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from core.config import load_config, save_agent_toggles, save_exclude_providers
from core.sources import SOURCES, SOURCE_BY_KEY, all_toggles, enabled_sources
from core import store, scoring, fetcher, ingest
from core.providers import job_provider
from core.areas import (
    REGIONS, REMOTE_FULL, REMOTE_PARTIAL, REMOTE_GENERIC, ONSITE, UNKNOWN,
    job_remote_level, job_prefecture,
)
from core.workdays import days_set, days_label

st.set_page_config(page_title="fl-cross v2", page_icon="🧭", layout="wide")

# ------------------------------------------------------------------
# 設定ロード（セッションで保持）
# ------------------------------------------------------------------
if "config" not in st.session_state:
    st.session_state.config = load_config()
config = st.session_state.config
profile = config.get("profile", {})

DEFAULT_KEYWORDS = ["AI", "LLM", "エージェント", "ローカルLLM", "Claude", "vLLM", "Ollama", "インフラ"]

# ==================================================================
# サイドバー
# ==================================================================
st.sidebar.title("🧭 fl-cross v2")
st.sidebar.caption(f"{profile.get('name','')} 向け横断ダッシュボード")

st.sidebar.subheader("検索先エージェント")
st.sidebar.caption("ON のサイトだけ取得・採点・表示されます")
toggles = all_toggles(config)
new_toggles = {}
for s in sorted(SOURCES, key=lambda x: x.priority):
    label = f"{s.name}  ·  {s.type}"
    new_toggles[s.key] = st.sidebar.checkbox(
        label, value=toggles[s.key], key=f"tg_{s.key}",
        help=(s.note + ("  ⚠ログイン/SPA: Chrome連携推奨" if s.login_required else "")),
    )
if new_toggles != toggles:
    # config(セッション) に反映 + ファイルへ保存
    config.setdefault("agents", {})
    for k, v in new_toggles.items():
        config["agents"].setdefault(k, {})["enabled"] = v
    try:
        save_agent_toggles(new_toggles)
    except Exception as e:  # noqa: BLE001
        st.sidebar.warning(f"設定保存に失敗: {e}")

# --- 提供元(provider)で横断除外 ---
st.sidebar.divider()
st.sidebar.subheader("提供元で除外")
st.sidebar.caption("取得元サイトに関わらず、提供元単位で除外（例: フリーランスHub経由のレバテック案件も消す）")
_jobs_for_prov = store.load_jobs()
providers_present = sorted({job_provider(j) for j in _jobs_for_prov if job_provider(j)})
current_excl = set(config.get("filters", {}).get("exclude_providers", []))
new_excl: set[str] = set()
if providers_present:
    with st.sidebar.expander(f"提供元 {len(providers_present)}件", expanded=bool(current_excl)):
        for p in providers_present:
            if st.checkbox(f"除外: {p}", value=(p in current_excl), key=f"excl_{p}"):
                new_excl.add(p)
    # 取得前から config に入っていて今は未取得の提供元も保持
    for p in current_excl:
        if p not in providers_present:
            new_excl.add(p)
else:
    st.sidebar.caption("（案件を取得すると提供元の一覧が出ます）")
    new_excl = set(current_excl)
if new_excl != current_excl:
    config.setdefault("filters", {})["exclude_providers"] = sorted(new_excl)
    try:
        save_exclude_providers(sorted(new_excl))
    except Exception as e:  # noqa: BLE001
        st.sidebar.warning(f"設定保存に失敗: {e}")
exclude_providers = set(config.get("filters", {}).get("exclude_providers", []))

st.sidebar.divider()
st.sidebar.subheader("フィルタ")
kw_text = st.sidebar.text_input("検索キーワード(スペース区切り)", value=" ".join(DEFAULT_KEYWORDS))
keywords = [k for k in kw_text.split() if k]
min_score = st.sidebar.slider("マッチ率の下限", 0, 100, 0, 5)

# --- リモート区分フィルタ ---
REMOTE_OPTIONS = [REMOTE_FULL, REMOTE_PARTIAL, REMOTE_GENERIC, ONSITE, UNKNOWN]
remote_sel = st.sidebar.multiselect(
    "リモート区分", REMOTE_OPTIONS, default=[REMOTE_FULL, REMOTE_PARTIAL, REMOTE_GENERIC],
    help="フルリモート / 一部リモート / リモート(区分不明) / 常駐 / 不明 から選択",
)
remote_set = set(remote_sel)

# --- 稼働日数(週何日)フィルタ ---
days_sel = st.sidebar.multiselect(
    "稼働日数(週)", [1, 2, 3, 4, 5], default=[],
    format_func=lambda d: f"週{d}日",
    help="選んだ日数で働ける案件のみ表示（例: 週3 を選ぶと 週3〜5 などの範囲案件もヒット）。未選択なら全件。",
)
days_filter = set(days_sel)
include_unknown_days = st.sidebar.checkbox(
    "稼働日数 不明も含める", value=True, help="週数の記載がない案件も表示する",
) if days_filter else True

# --- エリア(47都道府県)フィルタ ---
with st.sidebar.expander("エリア(47都道府県)で絞り込み"):
    st.caption("未選択なら全国。地方ごとにまとめて選べます。")
    pref_sel: list[str] = []
    for region, prefs in REGIONS.items():
        picked = st.multiselect(region, prefs, default=[], key=f"pref_{region}")
        pref_sel.extend(picked)
    include_unknown_area = st.checkbox("地域不明・記載なしも含める", value=True,
                                       help="リモート案件は勤務地未記載が多いため既定でON")
pref_set = set(pref_sel)

min_hourly = st.sidebar.number_input(
    "最低時給(円, 0=無視)", min_value=0, max_value=30000, value=0, step=500,
)

# --- LLM設定（深掘り分析） ---
st.sidebar.divider()
st.sidebar.subheader("LLM設定（深掘り分析）")
llm_cfg = config.setdefault("llm", {})
provider = st.sidebar.selectbox(
    "推論方法", ["ollama", "prompt-only"],
    index=0 if llm_cfg.get("provider", "ollama") == "ollama" else 1,
    help="ollama=ローカルLLMで分析 / prompt-only=プロンプトだけ出力（手動でClaude等へ）",
)
llm_cfg["provider"] = provider
base_url = st.sidebar.text_input("Ollama base_url", value=llm_cfg.get("base_url", "http://localhost:11434"))
llm_cfg["base_url"] = base_url
llm_cfg["timeout"] = st.sidebar.number_input("タイムアウト(秒)", 10, 600, int(llm_cfg.get("timeout", 180)), 10)

if st.sidebar.button("🔌 接続テスト / モデル一覧", use_container_width=True):
    st.session_state.llm_diag = scoring.ollama_diagnose(config)
diag = st.session_state.get("llm_diag")
_models = diag["models"] if diag else []
if diag:
    (st.sidebar.success if diag["ok"] else st.sidebar.error)(diag["message"])

# モデル選択（接続できていれば一覧から、なければ手入力）
cur_model = llm_cfg.get("model", "qwen2.5:32b")
if _models:
    idx = _models.index(cur_model) if cur_model in _models else 0
    llm_cfg["model"] = st.sidebar.selectbox("モデル", _models, index=idx)
else:
    llm_cfg["model"] = st.sidebar.text_input("モデル名", value=cur_model,
                                             help="接続テストを押すと一覧から選べます")

st.sidebar.divider()
st.sidebar.subheader("取得")

# --- ブラウザ自動取得（Playwright：全サイト対応） ---
import subprocess, sys as _sys
from pathlib import Path as _Path
from core import browser_fetch as _bf

pw_ok = _bf._is_playwright_available()
if st.sidebar.button("🌐 全サイト自動取得（ブラウザ）", use_container_width=True,
                     disabled=not pw_ok,
                     help="Playwrightで全有効サイト(SPA/ログイン含む)を取得。要ログインサイトは事前に下のログインが必要"):
    with st.spinner("ブラウザで全サイト取得中…（30〜90秒）"):
        proc = subprocess.run(
            [_sys.executable, "fetch_browser.py", "--keywords", *keywords],
            cwd=str(_Path(__file__).parent), capture_output=True, text=True, timeout=600,
        )
    st.session_state.browser_log = (proc.stdout or "") + (proc.stderr or "")
    st.rerun()

if not pw_ok:
    st.sidebar.caption("⚠ ブラウザ取得には Playwright が必要:\n`pip install playwright && playwright install chromium`")
else:
    profile_exists = (_Path.home() / ".fl-cross" / "pw-profile").exists()
    st.sidebar.caption(
        ("🔑 ログイン必須サイト(Findy/レバテック)は初回のみターミナルで:\n"
         "`python fetch_browser.py --login`\n"
         + ("（ログインプロファイル: 設定済み）" if profile_exists else "（未ログイン）"))
    )
if st.session_state.get("browser_log"):
    with st.sidebar.expander("ブラウザ取得ログ"):
        st.code(st.session_state["browser_log"][-2000:])

# --- httpx自動取得（軽量：サーバー描画サイトのみ） ---
if st.sidebar.button("🔄 httpx自動取得（軽量）", use_container_width=True,
                     help="ランサーズ・フリーランスボード等のサーバー描画サイトのみ。ブラウザ不要"):
    with st.spinner("取得中（ベストエフォート）..."):
        results = fetcher.fetch_all(config, keywords)
        total_added = total_updated = 0
        msgs = []
        for r in results:
            if r.jobs:
                a, u = store.upsert_jobs(r.jobs)
                total_added += a
                total_updated += u
            msgs.append(f"- {r.source.name}: {r.message}")
        st.session_state.fetch_report = msgs
        st.session_state.fetch_summary = f"新規 {total_added} / 更新 {total_updated}"
    st.rerun()

if "fetch_summary" in st.session_state:
    st.sidebar.success(st.session_state.fetch_summary)
    with st.sidebar.expander("httpx取得ログ"):
        st.markdown("\n".join(st.session_state.get("fetch_report", [])))

# ==================================================================
# メイン
# ==================================================================
st.title("横断案件ダッシュボード")

active = enabled_sources(config)
st.caption(
    "有効エージェント: " + (", ".join(s.name for s in active) if active else "なし") +
    f"  ／  キーワード: {' '.join(keywords) if keywords else '(なし)'}"
)

tab_jobs, tab_import, tab_help = st.tabs(["📋 案件一覧", "📥 取り込み(Chrome連携/手動)", "ℹ️ 使い方"])

# ---------------- 案件一覧 ----------------
with tab_jobs:
    jobs = store.load_jobs()
    # 有効エージェント(取得元サイト)のみ
    active_keys = {s.key for s in active}
    jobs = [j for j in jobs if j.source in active_keys]
    # 提供元(provider)除外（取得元に関わらず横断で消す）
    excluded_count = sum(1 for j in jobs if job_provider(j) in exclude_providers)
    jobs = [j for j in jobs if job_provider(j) not in exclude_providers]
    # 採点
    jobs = scoring.score_jobs(jobs, config)
    if exclude_providers:
        st.caption("除外中の提供元: " + ", ".join(sorted(exclude_providers)) + f"（{excluded_count}件を非表示）")
    # フィルタ
    def _passes(j):
        if (j.score or 0) < min_score:
            return False
        # リモート区分
        if remote_set and job_remote_level(j) not in remote_set:
            return False
        # 稼働日数(週)
        if days_filter:
            ds = days_set(j)
            if ds:
                if not (ds & days_filter):
                    return False
            elif not include_unknown_days:
                return False
        # エリア(都道府県)
        if pref_set:
            pf = job_prefecture(j)
            if pf:
                if pf not in pref_set:
                    return False
            else:
                if not include_unknown_area:
                    return False
        if min_hourly:
            hi = j.rate_hourly_max or ((j.rate_monthly_max or 0) // 160)
            if hi and hi < min_hourly:
                return False
        return True
    shown = [j for j in jobs if _passes(j)]

    c1, c2, c3 = st.columns(3)
    c1.metric("表示件数", len(shown))
    c2.metric("全件(有効サイト)", len(jobs))
    c3.metric("平均マッチ率", f"{(sum(j.score or 0 for j in shown)/len(shown)):.0f}" if shown else "—")

    if not shown:
        st.info("該当案件がありません。サイドバーで自動取得するか、「取り込み」タブからChrome連携/手動で案件を追加してください。")
    for j in shown:
        score = j.score or 0
        color = "🟢" if score >= 70 else ("🟡" if score >= 45 else "⚪")
        prov = job_provider(j)
        rate_disp = j.rate_text or "単価記載なし"
        header = f"{color} **{score:.0f}%**  ｜ 💰 **{rate_disp}**  ｜ {j.title}  ｜ 取得元:_{j.source_name}_ / 提供元:_{prov or '—'}_"
        with st.expander(header):
            meta = []
            if prov:
                meta.append(f"提供元: {prov}")
            if j.rate_text:
                meta.append(f"単価: {j.rate_text}")
            if j.work_style:
                meta.append(f"働き方: {j.work_style}")
            meta.append(f"リモート区分: {job_remote_level(j)}")
            meta.append(f"稼働日数: {days_label(j)}")
            _pf = job_prefecture(j)
            meta.append(f"エリア: {_pf or '不明/記載なし'}")
            if j.posted_date:
                meta.append(f"掲載: {j.posted_date}")
            st.caption("　｜　".join(meta) if meta else "")

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
                    st.caption("👇 下のプロンプトをコピーして、Claudeや他のLLMに貼り付けても分析できます")
                    st.code(res["prompt"], language="markdown")
            if j.llm_analysis:
                with st.expander("保存済みLLM分析"):
                    st.markdown(j.llm_analysis)

# ---------------- 取り込み ----------------
with tab_import:
    st.subheader("Chrome連携 / 手動で案件を取り込む")
    st.caption(
        "ログイン必須・SPAのサイト(レバテック/Findy等)は自動取得が難しいため、"
        "Claude in Chrome でページから案件を抜き出してJSONで貼り付けるか、手動で1件追加できます。"
    )
    src_key = st.selectbox(
        "取り込み先エージェント",
        options=[s.key for s in SOURCES],
        format_func=lambda k: SOURCE_BY_KEY[k].name,
    )

    st.markdown("**A) JSON(records)で一括取り込み**")
    st.code(
        '[\n  {"title":"生成AIエージェント基盤の開発","company":"X社",\n'
        '   "url":"https://...","rate_text":"〜120万円/月","work_style":"フルリモート 週4",\n'
        '   "description":"...","posted_date":"2026-06-25"}\n]',
        language="json",
    )
    json_text = st.text_area("JSONを貼り付け", height=180, key="json_in")
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
        m_desc = st.text_area("案件説明", height=140)
        submitted = st.form_submit_button("追加")
        if submitted:
            if not m_title.strip():
                st.error("タイトルは必須です")
            else:
                a, u = ingest.ingest_single(
                    src_key, title=m_title, company=m_company, url=m_url,
                    rate_text=m_rate, work_style=m_style, posted_date=m_date,
                    description=m_desc,
                )
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
1. **左サイドバーでエージェントをON/OFF** — 調べたいサイトだけ有効化（設定は `config.toml` に保存）。
2. **キーワード/フィルタ** を設定。
3. **「自動取得」** で公開ページをベストエフォート取得。ログイン必須サイトは「取り込み」タブへ。
4. **マッチ率(ルール)** 降順で一覧表示。内訳(KW/単価/リモート/新着)も確認可。
5. 気になる案件は **「LLM深掘り分析」** (ローカルOllama) で適合度・単価妥当性・提案ドラフトを生成。

### マッチ率の算出
- ルール採点 = キーワード一致 + 単価適合 + リモート/働き方 + 新着度（重みは `config.toml [scoring]`）。
- LLM深掘りは選んだ案件のみ。プライバシー重視ならローカルOllamaで完結。

### Chrome連携の流れ
レバテック等は Claude in Chrome で検索結果を開き、案件を上記JSON形式に整形 → 「取り込み」タブに貼り付け。
        """
    )
