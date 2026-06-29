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
| 🗂 **横断UI** | レバテック / フリーランスHub / Findy / クラウドワークステック / ランサーズ / フリーランスボードを1画面で比較 |
| 🎯 **マッチ率** | スキル・単価・働き方からルール採点。ローカルLLM（Ollama）で深掘りも可能 |
| 🔀 **取得元 ON/OFF** | 調べたいサイトだけ有効化（`config.toml` に保存） |
| 🚫 **提供元 除外** | アグリゲーター経由を含め、特定の提供元を横断除外 |
| 🔎 **多彩なフィルタ** | キーワード / マッチ率 / リモート区分 / 稼働日数(週) / エリア(47都道府県) / 最低時給 |
| 🌐 **全サイト自動取得** | SPA・ログイン必須サイトも Playwright で1ボタン取得 |

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

## 🌐 全サイト自動取得（Playwright）

SPA・ログイン必須サイトを含め、有効サイトを実ブラウザで描画して取得します。
ログイン情報は **永続プロファイル**（`~/.fl-cross/pw-profile`）に保存され、
一度ログインすれば以後の取得で再利用されます（**パスワードはアプリに保存されません**）。

**① 初回のみ：ログイン**

```bash
python fetch_browser.py --login
```

> ブラウザが画面ありで開きます。**Findy / レバテック** などにログインし、
> ターミナルで **Enter** を押すと閉じてログイン状態が保存されます。
> `Executable doesn't exist …` と出たら `python -m playwright install chromium` を実行。

**② 取得**

```bash
python fetch_browser.py
python fetch_browser.py --headful                       # 画面ありでデバッグ
python fetch_browser.py --keywords AI LLM エージェント    # キーワード指定
```

> アプリ起動中なら、サイドバーの **「🌐 全サイト自動取得（ブラウザ）」** ボタンでも実行できます。

---

## 📊 サイト別の取得方法（実測）

| サイト | ブラウザ取得 | httpx軽量取得 | 備考 |
|---|:---:|:---:|---|
| ランサーズ | ✅ | ✅ | サーバー描画 |
| フリーランスボード | ✅ | ✅ | 初期HTMLに案件あり |
| フリーランスHub | ✅ | ❌ | Vue SPA |
| クラウドワークステック | ✅ | ❌ | 完全クライアント描画 (Vite) |
| レバテックフリーランス | ✅ <sub>要ログイン</sub> | ❌ | ログイン必須 |
| Findy Freelance | ✅ <sub>要ログイン</sub> | ❌ | ログイン必須 ＋ SPA |
| ITプロパートナーズ | ✅ | ✅ | 週2-3日・リモート多め |
| Midworks | ✅ | ✅ | 言語/職種別の公開検索 |
| テクフリ | ✅ | ✅ | 高単価・マージン率公開 |
| PE-BANK | ✅ | ✅ | 地方案件も強い（万円表記） |

- **🌐 ブラウザ取得**：全サイト対応（推奨）。
- **🔄 httpx軽量取得**：ブラウザ不要。サーバー描画サイトのみ。
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
| `[scoring]` | ルール採点の重み（keyword / rate / remote / freshness） |
| `[filters]` | `exclude_providers` … 除外する提供元（例: `["レバテックフリーランス"]`） |
| `[llm]` | `provider`（ollama / prompt-only）・`model`・`base_url`・`timeout` |
| `[agents.<key>]` | 各取得元サイトの `enabled`（有効/無効） |

---

## 🧮 マッチ率の算出

**ルール採点（即時・無料）** = キーワード一致 + 単価適合 + リモート/働き方 + 新着度（重みは `[scoring]`）。

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
│  ├─ models.py            統一 Job スキーマ
│  ├─ store.py             data/jobs.json 読み書き・重複排除
│  ├─ sources.py           取得元サイト定義（ON/OFF・ログイン/JS要否）
│  ├─ fetcher.py           httpx 自動取得（サーバー描画サイト）
│  ├─ browser_fetch.py     Playwright 自動取得（SPA・ログイン必須）
│  ├─ normalize.py         単価/リモート/稼働日数/都道府県/スキルの正規化
│  ├─ areas.py             47都道府県マスタ・リモート区分判定
│  ├─ workdays.py          稼働日数（週何日）の判定
│  ├─ providers.py         提供元名の正規化
│  ├─ scoring.py           ハイブリッド採点（ルール + Ollama）+ LLM診断
│  └─ ingest.py            手動 / 取り込み
├─ data/sample_records.json   取り込みサンプル
├─ config.example.toml        設定サンプル（→ config.toml にコピー）
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
