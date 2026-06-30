<div align="center">

# 🧭 fl-cross

### フリーランス横断 共通ダッシュボード

バラバラなフリーランス案件探しを **1画面に共通化**。
データを取得・正規化して **マッチ率（適合度）** を算出し、自分に合う案件を効率的に見つけます。

<br>

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/UI-Streamlit-FF4B4B?logo=streamlit&logoColor=white)
![Playwright](https://img.shields.io/badge/Fetch-Playwright-2EAD33?logo=playwright&logoColor=white)
![Ollama](https://img.shields.io/badge/LLM-Ollama-000000?logo=ollama&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green.svg)

</div>

---

## ✨ 特長

| | |
|---|---|
| 🗂 **横断UI（13サイト）** | フリーランスHub / Findy / クラウドワークステック / ランサーズ / フリーランスボード / ITプロパートナーズ / Midworks / テクフリ / PE-BANK / FLEXY / **ギークスジョブ** / **テックストック** / **エンジニアファクトリー** を1画面で比較（レバテックも定義済み・既定オフ） |
| 🎯 **ハイブリッド・マッチ率** | スキル・単価・働き方からルール採点（重みはUIスライダーで調整）。キーワードは境界一致＋新着度は初観測日で実効化。ローカルLLM（Ollama）で深掘りも可能 |
| 🚀 **全取得（自動振り分け）** | 1ボタンで全サイト取得。`js_required / login_required` を見て **静的→httpx／JS・ログイン→Playwright** へ自動振り分け（ログインは永続プロファイルで保持） |
| 🔎 **多彩なフィルタ** | キーワード / マッチ率 / **月額レンジ(万円)** / リモート区分 / 稼働日数(週) / エリア(47都道府県) / 最低時給 |
| 🚫 **NGワード & 提供元 & 軽作業除外** | タイトル・社名・本文・提供元のブラックリスト、**クラウドソーシングの軽作業・プロジェクト総額(単価不明)の除外** を `config.toml` に保存（取得内容に依存しない） |
| 🏷 **ステータス管理** | 気になる/応募済み/見送り＋メモ。一覧でも `🆕NEW`・状態ラベルが見える |
| 🕒 **新着/経過の可視化** | 初観測日・最終確認日を記録。受付終了の可能性（`⚠️終了?`）も表示 |
| 🔁 **クロスサイト名寄せ** | 重複案件を一次ソース優先でグループ化し、各ソースの単価を並記（中抜き比較）。URL正規化でIDを安定化し再取得でも割れない |
| 📊 **サマリー & 並び替え** | 取得元別/単価分布/リモート/エリアの可視化。マッチ率/単価/新着/取得元/提供元で並べ替え |
| 🛡 **データ保全** | `jobs.json` を原子的保存＋自動バックアップ（`data/backups/`）。破損時は最新バックアップから自動復旧 |

> UIは **タブ構成**（案件一覧 / サマリー / 絞り込み詳細 / 設定 / 取り込み / 使い方）。よく使う操作はサイドバーに、細かい設定はタブに分けています。

---

## 🚀 クイックスタート

```bash
git clone <your-repo-url> fl-cross
cd fl-cross

# 1) 依存インストール
pip install -r requirements.txt

# 2) 全サイト自動取得を使うなら Chromium も取得
playwright install chromium        # うまくいかなければ: python -m playwright install chromium

# 3) 設定ファイルを用意（自分用に編集。.gitignore 済み）
cp config.example.toml config.toml

# 4) (任意) ローカルLLM深掘りを使うなら Ollama
#    ollama serve && ollama pull qwen2.5:7b
```

```bash
# 起動
streamlit run app.py        # コマンドが無ければ: python -m streamlit run app.py
```

ブラウザが開いたら、サイドバーで取得元・フィルタを設定し、取得 → マッチ率降順で一覧表示。

---

## 🌐 全サイト自動取得（httpx ＋ Playwright）

アプリの **「🚀 全取得（自動振り分け）」** ボタン、または `fetch_browser.py` が取得方法を **自動で振り分け** ます。

- **httpxで取れるサイト**（サーバー描画・ログイン不要）→ 軽量取得
- **SPA / ログイン必須**（クラウドワークステック・レバテック・Findy・FLEXY）→ Playwright

> フリーランスHub は実は SSR（サーバー描画）だったため、ブラウザ取得から **httpx取得に変更**（提供元＝エージェント名も取得）。

ログイン情報は **永続プロファイル**（`~/.fl-cross/pw-profile`）に保存され、
一度ログインすれば以後の取得で再利用されます（**パスワードはアプリに保存されません**）。

**① 初回のみ：ログイン**

```bash
python fetch_browser.py --login
```

> ブラウザが画面ありで開きます。**Findy / レバテック / FLEXY（サーキュレーション）** などに
> ログインし、ターミナルで **Enter** を押すと閉じてログイン状態が保存されます。
> `Executable doesn't exist …` と出たら `python -m playwright install chromium` を実行。

**② 取得**

```bash
python fetch_browser.py
python fetch_browser.py --headful                       # 画面ありでデバッグ
python fetch_browser.py --keywords AI LLM エージェント    # キーワード指定
```

> アプリ起動中なら、サイドバーの **「🚀 全取得（自動振り分け）」** ボタンでも実行できます（静的=httpx／JS・ログイン=ブラウザを自動振り分け）。個別の「🔄 httpx自動取得」「🌐 ブラウザ取得」も残しています。

---

## 📊 サイト別の取得方法（実測）

| サイト | 取得方法 | 備考 |
|---|---|---|
| フリーランスHub | httpx | Nuxt SSR（アグリゲーター36万件超）。提供元も取得 |
| ランサーズ | httpx | サーバー描画 |
| フリーランスボード | httpx | 初期HTMLに案件あり |
| ITプロパートナーズ | httpx | 週2-3日・リモート多め |
| Midworks | httpx | 言語/職種別の公開検索 |
| テクフリ | httpx | 高単価・マージン率公開 |
| PE-BANK | httpx | 地方案件も強い（万円表記） |
| ギークスジョブ | httpx | 老舗・案件1万件超（静的HTML） |
| テックストック | httpx | INTLOOP運営・高単価帯（静的HTML） |
| エンジニアファクトリー | httpx | エンド直・高単価（静的HTML） |
| クラウドワークステック | ブラウザ | 完全クライアント描画 (Vite) |
| レバテックフリーランス | ブラウザ＋ログイン | 高単価・非公開多め |
| Findy Freelance | ブラウザ＋ログイン | ログイン後 `/works` で検索 |
| FLEXY（サーキュレーション） | ブラウザ＋ログイン | `pro.circu.info`。ハイスキル・高単価 |

- **🚀 全取得（自動振り分け）** / **`python fetch_browser.py`**：httpx と Playwright を自動で振り分けて全サイト取得（推奨）。
- **🔄 httpx自動取得（軽量）**：アプリのボタン。サーバー描画サイトのみ・ブラウザ不要。
- **📥 手動取り込み**：任意の案件をJSON貼り付け or 1件追加。

<details>
<summary>手動取り込みのJSON形式</summary>

```json
[
  {"title": "...", "company": "...", "url": "https://...",
   "rate_text": "〜120万円/月", "work_style": "フルリモート 週4",
   "description": "...", "posted_date": "2026-06-25"}
]
```
</details>

---

## ⚙️ 設定（`config.toml`）

`config.example.toml` をコピーして編集します（`config.toml` は `.gitignore` 済み）。

| セクション | 内容 |
|---|---|
| `[profile]` | 名前・強み（`strong_skills`）・`match_keywords`・希望単価・リモート希望 |
| `[scoring]` | ルール採点の重み（keyword / rate / remote / freshness。UIスライダーからも保存） |
| `[filters]` | `exclude_providers`（提供元ブラックリスト）・`ng_words`（NGワード）・`exclude_microtasks` / `microtask_words`（クラウドソーシングの軽作業・プロジェクト総額の除外） |
| `[llm]` | `provider`（ollama / prompt-only）・`model`・`base_url`・`timeout`（UIで変更すると自動保存） |
| `[agents.<key>]` | 各取得元サイトの `enabled`（有効/無効） |

---

## 🧮 マッチ率の算出

**ルール採点（即時・無料）** = キーワード一致 + 単価適合 + リモート/働き方 + 新着度（重みは `[scoring]`）。
キーワードは英数字短語（AI/Go/C# 等）を境界一致で誤ヒット抑制、新着度は掲載日が無ければ初観測日（`first_seen`）を代理に使用。

**LLM深掘り（任意）** = 選んだ案件のみローカルOllamaで分析し、適合度内訳・単価妥当性・
レッドフラッグ・提案ドラフトを生成。サイドバーで接続テスト・モデル選択ができ、
Ollamaが無い場合はプロンプトをコピーして他のLLMに投げることも可能。

---

## 📁 ディレクトリ構成

```
fl-cross/
├─ app.py                  共通UI（Streamlit）
├─ fetch_browser.py        全サイト自動取得CLI（Playwright / --login で初回ログイン）
├─ core/
│  ├─ config.py            設定読み込み + エージェント/提供元の保存
│  ├─ models.py            統一 Job スキーマ（URL正規化でID安定化）
│  ├─ store.py             data/jobs.json 読み書き・重複排除（原子的保存＋自動バックアップ/復旧）
│  ├─ sources.py           取得元サイト定義（13サイト・ON/OFF・ログイン/JS要否）
│  ├─ fetcher.py           httpx 自動取得（サーバー描画サイト・サイト別パーサ）
│  ├─ browser_fetch.py     Playwright 自動取得（SPA・ログイン必須）
│  ├─ normalize.py         単価/リモート/稼働日数/都道府県/スキルの正規化
│  ├─ areas.py             47都道府県マスタ・リモート区分判定
│  ├─ workdays.py          稼働日数（週何日）の判定
│  ├─ providers.py         提供元名の正規化
│  ├─ dedup.py             クロスサイト名寄せ（一次ソース優先）
│  ├─ scoring.py           ハイブリッド採点（ルール + Ollama）+ LLM診断
│  └─ ingest.py            手動 / 取り込み
├─ data/sample_records.json   取り込みサンプル
├─ data/backups/              jobs.json の自動バックアップ（直近10件・.gitignore済み）
├─ config.example.toml        設定サンプル（→ config.toml にコピー）
├─ docs/note/                 紹介記事（Note）
├─ selftest.py                スモークテスト
└─ requirements.txt
```

---

## 🧪 テスト

```bash
python selftest.py   # 単価パース・採点順序・store往復を検証
```

---

## ⚠️ 注意

- スクレイピングは各サイトの利用規約・robots.txt に従ってください。過度なアクセスは避けてください。
- マッチ率・LLM分析は参考情報です。応募の最終判断はご自身で。
- 本ツールは個人の案件探しの効率化を目的とした非公式ツールです。

---

## 📄 License

[MIT](./LICENSE) License
