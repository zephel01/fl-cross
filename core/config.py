"""設定の読み込み。config.toml をマージして返す。"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

try:
    import tomllib  # py3.11+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.toml"
EXAMPLE_PATH = ROOT / "config.example.toml"

DEFAULT_CONFIG: dict[str, Any] = {
    "profile": {
        "name": "Your Name",
        "strong_skills": [],
        "match_keywords": ["AI", "LLM", "エージェント", "Python"],
        "target_rate_min": 8000,
        "target_rate_max": 15000,
        "target_monthly_min": 700000,
        "target_monthly_max": 1200000,
        "preferred_remote": True,
        "preferred_work_style": "フルリモート",
        "location": "東京",
    },
    "llm": {
        "provider": "ollama",
        "model": "qwen2.5:32b",
        "base_url": "http://localhost:11434",
        "timeout": 180,
    },
    "scoring": {
        "weight_keyword": 45,
        "weight_rate": 25,
        "weight_remote": 15,
        "weight_freshness": 15,
    },
    "filters": {
        # 取得元サイトに関わらず、ここに挙げた提供元(provider)の案件を除外する
        "exclude_providers": [],
        # タイトル・社名・本文・提供元にこれらの語を含む案件を除外（ブラックリスト）
        "ng_words": [],
    },
    "agents": {},
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path: Path | None = None) -> dict[str, Any]:
    # config.toml が無ければ config.example.toml をフォールバックに使う
    p = path or (CONFIG_PATH if CONFIG_PATH.exists() else EXAMPLE_PATH)
    cfg = {k: (dict(v) if isinstance(v, dict) else v) for k, v in DEFAULT_CONFIG.items()}
    if p.exists():
        try:
            with open(p, "rb") as f:
                user = tomllib.load(f)
            cfg = _deep_merge(cfg, user)
        except Exception as e:  # noqa: BLE001
            print(f"[fl-cross] config 読み込み失敗、デフォルト使用: {e}", file=sys.stderr)
    return cfg


def save_agent_toggles(toggles: dict[str, bool], path: Path | None = None) -> None:
    """UIからのエージェントON/OFFを config.toml の [agents] に書き戻す。

    既存の他セクションを壊さないよう、行ベースで [agents.*] ブロックのみ置換する。
    """
    p = path or CONFIG_PATH
    text = p.read_text(encoding="utf-8") if p.exists() else ""
    lines = text.splitlines()
    out: list[str] = []
    skip_block = False
    seen = set()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("[agents."):
            key = stripped[len("[agents."):].rstrip("]")
            seen.add(key)
            val = toggles.get(key)
            if val is None:
                out.append(line)
                i += 1
                continue
            out.append(line)
            out.append(f"enabled = {'true' if val else 'false'}")
            # 元の enabled 行をスキップ
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith("["):
                if lines[j].strip().startswith("enabled"):
                    j += 1
                    continue
                out.append(lines[j])
                j += 1
            i = j
            continue
        out.append(line)
        i += 1

    # config に無かった新規エージェントを末尾に追加
    extra = [k for k in toggles if k not in seen]
    if extra:
        if out and out[-1].strip():
            out.append("")
        for k in extra:
            out.append(f"[agents.{k}]")
            out.append(f"enabled = {'true' if toggles[k] else 'false'}")

    p.write_text("\n".join(out) + "\n", encoding="utf-8")


def save_filter_list(key: str, values: list[str], path: Path | None = None) -> None:
    """[filters] 内の任意のリストキー（exclude_providers / ng_words 等）を書き戻す。"""
    p = path or CONFIG_PATH
    lines = (p.read_text(encoding="utf-8").splitlines() if p.exists() else [])
    fmt = _fmt_list(key, values)
    out: list[str] = []
    i = 0
    found = False
    while i < len(lines):
        line = lines[i]
        if line.strip() == "[filters]":
            found = True
            out.append(line)
            j = i + 1
            wrote = False
            while j < len(lines) and not lines[j].strip().startswith("["):
                s = lines[j].strip()
                if s.startswith(key):
                    if not wrote:
                        out.append(fmt)
                        wrote = True
                else:
                    out.append(lines[j])
                j += 1
            if not wrote:
                out.append(fmt)
            i = j
            continue
        out.append(line)
        i += 1
    if not found:
        if out and out[-1].strip():
            out.append("")
        out.append("[filters]")
        out.append(fmt)
    p.write_text("\n".join(out) + "\n", encoding="utf-8")


def save_llm_config(llm: dict, path: Path | None = None) -> None:
    """[llm] の provider/model/base_url/timeout を config.toml に書き戻す。"""
    keys = ["provider", "model", "base_url", "timeout"]

    def fmt(k: str) -> str:
        v = llm.get(k)
        if k == "timeout":
            return f"timeout = {int(v) if v is not None else 180}"
        return f'{k} = "{str(v)}"'

    p = path or CONFIG_PATH
    lines = (p.read_text(encoding="utf-8").splitlines() if p.exists() else [])
    out: list[str] = []
    i = 0
    in_sec = False
    written: set[str] = set()
    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if s.startswith("[") and s != "[llm]":
            # [llm] セクションを抜ける直前に、未記入キーを補完
            if in_sec:
                for k in keys:
                    if k not in written:
                        out.append(fmt(k))
                        written.add(k)
            in_sec = False
        if s == "[llm]":
            in_sec = True
            out.append(line)
            i += 1
            continue
        if in_sec and "=" in s and s.split("=")[0].strip() in keys:
            k = s.split("=")[0].strip()
            out.append(fmt(k))
            written.add(k)
            i += 1
            continue
        out.append(line)
        i += 1
    if in_sec:  # ファイル末尾が [llm] だった場合
        for k in keys:
            if k not in written:
                out.append(fmt(k))
    if not any(l.strip() == "[llm]" for l in lines):
        out.append("")
        out.append("[llm]")
        for k in keys:
            out.append(fmt(k))
    p.write_text("\n".join(out) + "\n", encoding="utf-8")


def save_scoring_weights(weights: dict[str, int], path: Path | None = None) -> None:
    """[scoring] の weight_* を config.toml に書き戻す。"""
    p = path or CONFIG_PATH
    lines = (p.read_text(encoding="utf-8").splitlines() if p.exists() else [])
    out: list[str] = []
    i = 0
    in_scoring = False
    written = set()
    while i < len(lines):
        line = lines[i]
        st = line.strip()
        if st.startswith("[") and st != "[scoring]":
            in_scoring = False
        if st == "[scoring]":
            in_scoring = True
            out.append(line)
            i += 1
            continue
        if in_scoring and "=" in st and st.split("=")[0].strip() in weights:
            key = st.split("=")[0].strip()
            out.append(f"{key} = {int(weights[key])}")
            written.add(key)
            i += 1
            continue
        out.append(line)
        i += 1
    # [scoring] が無ければ末尾に追加
    if not any(l.strip() == "[scoring]" for l in lines):
        out.append("")
        out.append("[scoring]")
        for k, v in weights.items():
            out.append(f"{k} = {int(v)}")
    p.write_text("\n".join(out) + "\n", encoding="utf-8")


def save_exclude_providers(providers: list[str], path: Path | None = None) -> None:
    save_filter_list("exclude_providers", providers, path)


def save_ng_words(words: list[str], path: Path | None = None) -> None:
    save_filter_list("ng_words", words, path)


def _fmt_list(key: str, values: list[str]) -> str:
    items = ", ".join('"' + str(x).replace('"', "") + '"' for x in values)
    return f"{key} = [{items}]"
