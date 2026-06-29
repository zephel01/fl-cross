"""47都道府県エリアマスタ ＋ リモート区分・都道府県の判定。

- リモート区分: フルリモート / 一部リモート / リモート(区分不明) / 常駐 / 不明
- 都道府県: テキストから47都道府県を検出
"""
from __future__ import annotations

# 地方ごとの47都道府県（UIのグループ表示用）
REGIONS: dict[str, list[str]] = {
    "北海道・東北": ["北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県"],
    "関東": ["茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県"],
    "中部": ["新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県", "岐阜県", "静岡県", "愛知県"],
    "近畿": ["三重県", "滋賀県", "京都府", "大阪府", "兵庫県", "奈良県", "和歌山県"],
    "中国": ["鳥取県", "島根県", "岡山県", "広島県", "山口県"],
    "四国": ["徳島県", "香川県", "愛媛県", "高知県"],
    "九州・沖縄": ["福岡県", "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県"],
}

PREFECTURES: list[str] = [p for ps in REGIONS.values() for p in ps]

# 「東京」「大阪」など接尾辞なし表記も拾うための別名
_SHORT = {p: p.replace("都", "").replace("府", "").replace("県", "") for p in PREFECTURES}

# リモート区分の優先判定（上から順にマッチ）
REMOTE_FULL = "フルリモート"
REMOTE_PARTIAL = "一部リモート"
REMOTE_GENERIC = "リモート"
ONSITE = "常駐"
UNKNOWN = "不明"

REMOTE_LEVELS = [REMOTE_FULL, REMOTE_PARTIAL, REMOTE_GENERIC, ONSITE, UNKNOWN]


def remote_level(text: str) -> str:
    """テキストからリモート区分を判定。"""
    if not text:
        return UNKNOWN
    t = text
    if "フルリモート" in t or "完全リモート" in t:
        return REMOTE_FULL
    if "一部リモート" in t or "リモートメイン" in t or "基本リモート" in t or "リモート中心" in t:
        return REMOTE_PARTIAL
    if "リモート可" in t or "リモートOK" in t or "リモート" in t or "在宅" in t:
        return REMOTE_GENERIC
    if "常駐" in t or "出社" in t:
        return ONSITE
    return UNKNOWN


def detect_prefecture(text: str) -> str:
    """テキストから都道府県を1つ検出（最初にヒットしたもの）。無ければ ''。"""
    if not text:
        return ""
    # まず正式名称
    for p in PREFECTURES:
        if p in text:
            return p
    # 短縮名（東京/大阪 等）。東京都など既出は上で取れる。
    for p, s in _SHORT.items():
        if s and s in text:
            return p
    return ""


def region_of(pref: str) -> str:
    for region, ps in REGIONS.items():
        if pref in ps:
            return region
    return ""


# Job から区分・都道府県を導出（既存データにフィールドが無くてもテキストから推定）
def job_remote_level(job) -> str:
    explicit = (getattr(job, "remote_type", "") or "").strip()
    if explicit in REMOTE_LEVELS:
        return explicit
    text = " ".join([
        getattr(job, "work_style", "") or "",
        getattr(job, "description", "") or "",
        getattr(job, "title", "") or "",
    ])
    lvl = remote_level(text)
    if lvl == UNKNOWN and getattr(job, "remote", None) is True:
        return REMOTE_GENERIC
    if lvl == UNKNOWN and getattr(job, "remote", None) is False:
        return ONSITE
    return lvl


def job_prefecture(job) -> str:
    explicit = (getattr(job, "prefecture", "") or "").strip()
    if explicit:
        return explicit
    text = " ".join([
        getattr(job, "location", "") or "",
        getattr(job, "work_style", "") or "",
        getattr(job, "description", "") or "",
        getattr(job, "title", "") or "",
    ])
    return detect_prefecture(text)
