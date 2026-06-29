"""ハイブリッド・マッチ率算出。

1) rule_score: ルールベース(即時・無料)
   - keyword : 強みキーワードの重なり
   - rate    : 単価レンジ適合
   - remote  : リモート/働き方適合
   - freshness: 新着度
2) llm_review: 選んだ案件だけ Ollama で深掘り分析（任意）
"""
from __future__ import annotations

import re
from datetime import datetime, date
from typing import Optional

from .models import Job


# ------------------------------------------------------------------
# ルール採点
# ------------------------------------------------------------------

def _norm(s: str) -> str:
    return (s or "").lower()


def _keyword_score(job: Job, keywords: list[str]) -> float:
    """説明・タイトル・スキルに含まれる強みKWの割合 (0..1)。"""
    if not keywords:
        return 0.0
    haystack = _norm(" ".join([job.title, job.description, " ".join(job.skills)]))
    hits = 0
    for kw in keywords:
        k = _norm(kw)
        if k and k in haystack:
            hits += 1
    # 重なり数を対数的に評価（多すぎると飽和）。3個一致で~0.6、6個で~0.85目安。
    ratio = hits / max(len(keywords), 1)
    # 一致数自体もボーナス
    boost = min(hits / 6.0, 1.0)
    return min(0.5 * ratio + 0.5 * boost, 1.0)


def _hourly_from_job(job: Job) -> Optional[tuple[int, int]]:
    """時給レンジを推定。月額しか無ければ稼働160h/月で時給換算。"""
    if job.rate_hourly_min or job.rate_hourly_max:
        lo = job.rate_hourly_min or job.rate_hourly_max or 0
        hi = job.rate_hourly_max or job.rate_hourly_min or 0
        return (lo, hi)
    if job.rate_monthly_min or job.rate_monthly_max:
        lo = (job.rate_monthly_min or job.rate_monthly_max or 0) // 160
        hi = (job.rate_monthly_max or job.rate_monthly_min or 0) // 160
        return (lo, hi)
    return None


def _rate_score(job: Job, profile: dict) -> float:
    """ターゲット時給レンジとの重なり (0..1)。不明なら中立 0.5。"""
    rng = _hourly_from_job(job)
    if not rng or not any(rng):
        return 0.5
    lo, hi = rng
    tmin = profile.get("target_rate_min", 8000)
    tmax = profile.get("target_rate_max", 15000)
    job_mid = (lo + hi) / 2 if (lo and hi) else (lo or hi)
    if job_mid <= 0:
        return 0.5
    if job_mid >= tmax:
        return 1.0
    if job_mid <= tmin * 0.6:
        return 0.15
    # tmin*0.6 .. tmax を 0.3..1.0 に線形マップ
    span = tmax - tmin * 0.6
    return max(0.15, min(1.0, 0.3 + 0.7 * (job_mid - tmin * 0.6) / span))


REMOTE_WORDS = ["リモート", "remote", "在宅", "フルリモート"]
LOWLOAD_WORDS = ["週1", "週2", "週3", "週4", "稼働日数", "副業", "時短"]


def _remote_score(job: Job, profile: dict) -> float:
    text = _norm(" ".join([job.work_style, job.description, job.title]))
    wants_remote = profile.get("preferred_remote", True)
    score = 0.5
    is_remote = job.remote
    if is_remote is None:
        is_remote = any(w in text for w in REMOTE_WORDS)
    if wants_remote:
        score = 1.0 if is_remote else 0.35
    if any(w in text for w in LOWLOAD_WORDS):
        score = min(1.0, score + 0.15)
    return score


def _parse_date(s: str) -> Optional[date]:
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    return None


def _freshness_score(job: Job, today: Optional[date] = None) -> float:
    today = today or date.today()
    d = _parse_date(job.posted_date)
    if not d:
        return 0.5  # 不明は中立
    days = (today - d).days
    if days <= 3:
        return 1.0
    if days <= 7:
        return 0.85
    if days <= 14:
        return 0.65
    if days <= 30:
        return 0.45
    return 0.25


def rule_score(job: Job, config: dict) -> tuple[float, dict[str, float]]:
    profile = config.get("profile", {})
    sc = config.get("scoring", {})
    w_kw = sc.get("weight_keyword", 45)
    w_rate = sc.get("weight_rate", 25)
    w_remote = sc.get("weight_remote", 15)
    w_fresh = sc.get("weight_freshness", 15)
    total_w = max(w_kw + w_rate + w_remote + w_fresh, 1)

    kw = _keyword_score(job, profile.get("match_keywords", []))
    rate = _rate_score(job, profile)
    remote = _remote_score(job, profile)
    fresh = _freshness_score(job)

    breakdown = {
        "keyword": round(kw * 100, 1),
        "rate": round(rate * 100, 1),
        "remote": round(remote * 100, 1),
        "freshness": round(fresh * 100, 1),
    }
    score = (kw * w_kw + rate * w_rate + remote * w_remote + fresh * w_fresh) / total_w * 100
    return round(score, 1), breakdown


def score_jobs(jobs: list[Job], config: dict) -> list[Job]:
    for j in jobs:
        s, bd = rule_score(j, config)
        j.score = s
        j.score_breakdown = bd
    jobs.sort(key=lambda x: (x.score or 0), reverse=True)
    return jobs


# ------------------------------------------------------------------
# LLM 深掘り（任意・選択した案件のみ）
# ------------------------------------------------------------------

def build_analysis_prompt(job: Job, config: dict) -> str:
    profile = config.get("profile", {})
    skills = "\n".join(f"- {s}" for s in profile.get("strong_skills", []))
    return f"""あなたは日本のAI/LLMインフラ・エージェント専門フリーランス「{profile.get('name','')}」の\
キャリアアドバイザーです。彼の強みは:

{skills}

ターゲット単価: {profile.get('target_rate_min'):,}〜{profile.get('target_rate_max'):,}円/時間
希望: {profile.get('preferred_work_style','')}  拠点: {profile.get('location','')}

以下の案件を彼の視点で厳しく現実的に分析し、Markdownで出力してください。

## 1. 適合度スコア (100点満点)
- 総合 / AI Agent / ローカルLLMインフラ / セキュリティ / Python・DevOps の内訳
## 2. 市場想定単価 (2026年日本フリーランス相場) と根拠
## 3. 活かせる強み
## 4. レッドフラッグ / 要確認
## 5. 初回提案ポイント・聞くべき質問・200字提案ドラフト
## 6. 応募推奨度(★5段階)と理由

---
【案件】
タイトル: {job.title}
企業: {job.company}
単価表記: {job.rate_text}
働き方: {job.work_style}  リモート: {job.remote}
URL: {job.url}

{job.description}
"""


def _base_url(config: dict) -> str:
    return config.get("llm", {}).get("base_url", "http://localhost:11434").rstrip("/")


def ollama_diagnose(config: dict) -> dict:
    """Ollama接続診断。{ok, models, message} を返す。httpx直叩きで依存を最小化。"""
    base = _base_url(config)
    try:
        import httpx
    except ImportError:
        return {"ok": False, "models": [], "message": "httpx 未インストール (pip install httpx)"}
    try:
        r = httpx.get(base + "/api/tags", timeout=5.0)
        r.raise_for_status()
        models = [m.get("name", "") for m in r.json().get("models", [])]
        if not models:
            return {"ok": True, "models": [], "message": f"接続OK ({base}) だがモデル未取得。`ollama pull <model>` が必要"}
        return {"ok": True, "models": models, "message": f"接続OK ({base}) / モデル {len(models)}件"}
    except Exception as e:  # noqa: BLE001
        hint = "Ollamaが起動しているか確認 (`ollama serve`)、base_urlを確認"
        return {"ok": False, "models": [], "message": f"接続NG ({base}): {type(e).__name__}: {e} — {hint}"}


def llm_review(job: Job, config: dict) -> dict:
    """LLM深掘り分析。構造化結果を返す:
    {ok: bool, text: str, error: str, prompt: str}
    provider != ollama の場合は ok=False, prompt 同梱（手動コピー用）。
    """
    prompt = build_analysis_prompt(job, config)
    llm = config.get("llm", {})
    if llm.get("provider") != "ollama":
        return {"ok": False, "text": "", "error": "provider が ollama ではありません（prompt-only）。下のプロンプトをコピーしてClaude等に投げてください。", "prompt": prompt}
    try:
        import httpx
    except ImportError:
        return {"ok": False, "text": "", "error": "httpx 未インストール (pip install httpx)", "prompt": prompt}
    base = _base_url(config)
    model = llm.get("model", "qwen2.5:32b")
    try:
        r = httpx.post(
            base + "/api/chat",
            json={"model": model, "messages": [{"role": "user", "content": prompt}], "stream": False},
            timeout=float(llm.get("timeout", 180)),
        )
        if r.status_code == 404:
            return {"ok": False, "text": "", "error": f"モデル '{model}' が見つかりません。`ollama pull {model}` を実行するか、別モデルを選択してください。", "prompt": prompt}
        r.raise_for_status()
        data = r.json()
        content = (data.get("message") or {}).get("content", "")
        if not content:
            return {"ok": False, "text": "", "error": f"応答が空でした（model={model}）。レスポンス: {str(data)[:200]}", "prompt": prompt}
        return {"ok": True, "text": content, "error": "", "prompt": prompt}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "text": "", "error": f"{type(e).__name__}: {e} — Ollama起動/base_url/モデルを確認", "prompt": prompt}
