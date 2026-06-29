"""Playwright によるブラウザ自動取得。

httpx では取れない JS描画(SPA)・ログイン必須サイトを、実ブラウザで描画して取得する。
ログインは「永続プロファイル」に保存され、一度ログインすれば以後は自動取得で再利用される。

セットアップ:
    pip install playwright
    playwright install chromium

初回ログイン（画面ありで起動し、対象サイトにログインして閉じる）:
    python fetch_browser.py --login

全有効サイトを自動取得:
    python fetch_browser.py

プロファイル保存先: ~/.fl-cross/pw-profile （パスワードはアプリに保存しない）
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Optional

from .sources import Source, SOURCE_BY_KEY, enabled_sources
from . import normalize as norm
from .models import Job

PROFILE_DIR = Path.home() / ".fl-cross" / "pw-profile"

# 47都道府県（抽出JSに埋め込む）
_PREF_JS = (
    "['北海道','青森県','岩手県','宮城県','秋田県','山形県','福島県','茨城県','栃木県',"
    "'群馬県','埼玉県','千葉県','東京都','神奈川県','新潟県','富山県','石川県','福井県',"
    "'山梨県','長野県','岐阜県','静岡県','愛知県','三重県','滋賀県','京都府','大阪府',"
    "'兵庫県','奈良県','和歌山県','鳥取県','島根県','岡山県','広島県','山口県','徳島県',"
    "'香川県','愛媛県','高知県','福岡県','佐賀県','長崎県','熊本県','大分県','宮崎県',"
    "'鹿児島県','沖縄県']"
)

# 各サイトの抽出JS。window で記録される配列を返す（[{title,url,company,rate_text,work_style,location,description}]）。
_EXTRACTORS: dict[str, str] = {
    # フリーランスHub（Vue SPA / ログイン有無で入口URL差異あり）
    "freelance_hub": f"""
    () => {{
      const PREF={_PREF_JS}; const out=[]; const seen=new Set();
      for (const a of document.querySelectorAll('a[href*="input/project/"]')) {{
        const m=a.getAttribute('href').match(/project\\/(\\d+)/); if(!m) continue;
        const id=m[1]; if(seen.has(id)) continue;
        let card=a; for(let i=0;i<9&&card.parentElement;i++){{card=card.parentElement; if((card.textContent||'').includes('円/')) break;}}
        let text=(card.textContent||'').replace(/\\s+/g,' ').trim(); if(text.length<20) continue;
        let t=text.replace(/^(NEW|注目|急募|\\s)+/,'');
        const cut=t.search(/(フルリモート|リモート可|一部リモート|[\\d,]+\\s*円)/);
        let title=(cut>0?t.slice(0,cut):t.slice(0,50)).trim().slice(0,70);
        const rate=((text.match(/([\\d,]+)\\s*円\\s*\\/\\s*月/)||[])[1])||'';
        const remote=/フルリモート|リモート可|一部リモート|リモート/.test(text);
        const week=((text.match(/週\\s*([1-5])/)||[])[1])||'';
        const via=(text.match(/提供元[:：]\\s*([^ 応]+)/)||['',''])[1].slice(0,16);
        let pf=''; for(const p of PREF){{ if(text.includes(p)){{pf=p;break;}} }}
        seen.add(id);
        out.push({{title, url:'https://freelance-hub.jp/project/detail/'+id+'/', company:via,
          rate_text: rate?rate+'円/月':'', work_style:(remote?'リモート ':'')+(week?'週'+week:''),
          location:pf, description:title}});
        if(out.length>=40) break;
      }}
      return out;
    }}
    """,
    # レバテックフリーランス（ログイン必須）
    "levtech": f"""
    () => {{
      const PREF={_PREF_JS}; const out=[]; const seen=new Set();
      for (const a of document.querySelectorAll('a[href*="/project/detail/"]')) {{
        const m=a.getAttribute('href').match(/detail\\/(\\d+)/); if(!m) continue;
        const id=m[1]; if(seen.has(id)) continue;
        let card=a; for(let i=0;i<9&&card.parentElement;i++){{card=card.parentElement; const x=card.innerText||''; if(x.includes('円')&&x.length>80) break;}}
        const text=(card.innerText||'').replace(/\\s+/g,' ').trim(); if(text.length<25) continue;
        let title=(a.innerText||'').replace(/\\s+/g,' ').trim();
        if(title.length<6) title=(text.match(/【[^】]*】[^¥\\n]{{0,40}}/)||[''])[0];
        title=title.replace(/のフリーランス求人.*$/,'').slice(0,70);
        const rate=((text.match(/([\\d,]+)\\s*円\\s*[／/]\\s*月/)||[])[1])||'';
        const remote=/フルリモート|リモートOK|リモート可|一部リモート|リモート/.test(text);
        const week=((text.match(/週\\s*([1-5])/)||[])[1])||'';
        let pf=''; for(const p of PREF){{ if(text.includes(p)){{pf=p;break;}} }}
        seen.add(id);
        out.push({{title, url:'https://freelance.levtech.jp/project/detail/'+id+'/', company:'レバテックフリーランス',
          rate_text: rate?rate+'円/月':'', work_style:(remote?'リモート ':'')+(week?'週'+week:''),
          location:pf, description:title}});
        if(out.length>=40) break;
      }}
      return out;
    }}
    """,
    # Findy Freelance（ログイン必須 / 詳細はボタン）
    "findy": f"""
    () => {{
      const PREF={_PREF_JS}; const out=[]; const seen=new Set();
      const btns=Array.from(document.querySelectorAll('a,button')).filter(b=>(b.textContent||'').includes('案件の詳細'));
      for(const b of btns) {{
        let card=b; for(let i=0;i<8&&card.parentElement;i++){{card=card.parentElement; const tx=card.innerText||''; if(tx.includes('円 / 月')&&tx.length>120) break;}}
        const text=(card.innerText||'').replace(/\\s+/g,' ').trim();
        let title=(text.match(/【[^】]*】[^¥\\n]{{0,50}}/)||[''])[0].trim().slice(0,70);
        const rate=((text.match(/([\\d,]+)\\s*円\\s*\\/\\s*月/)||[])[1])||'';
        const week=((text.match(/週\\s*([1-5])日/)||[])[1])||'';
        const remote=/フルリモート|一部リモート|リモートメイン/.test(text);
        let pf=''; for(const p of PREF){{ if(text.includes(p)){{pf=p;break;}} }}
        const key=title+rate; if(seen.has(key)||!title) continue; seen.add(key);
        out.push({{title, url:'https://freelance.findy-code.io/works', company:'Findy',
          rate_text: rate?rate+'円/月':'', work_style:(remote?'リモート ':'')+(week?'週'+week:''),
          location:pf, description:title}});
        if(out.length>=30) break;
      }}
      return out;
    }}
    """,
    # クラウドワークステック（Vite CSR）
    "crowdworks_tech": f"""
    () => {{
      const PREF={_PREF_JS}; const out=[]; const seen=new Set();
      for (const a of document.querySelectorAll('a[href*="job_offer"]')) {{
        const h=a.getAttribute('href')||''; const m=h.match(/(\\d{{3,}})/); if(!m) continue;
        const id=m[1]; if(seen.has(id)) continue;
        let card=a; for(let i=0;i<8&&card.parentElement;i++){{card=card.parentElement; if((card.innerText||'').match(/[\\d,]+\\s*円/)) break;}}
        const text=(card.innerText||'').replace(/\\s+/g,' ').trim(); if(text.length<15) continue;
        let title=(a.textContent||'').trim(); if(title.length<6) title=(text.match(/【[^】]*】[^\\n]{{0,40}}/)||[''])[0];
        title=title.slice(0,70);
        const rate=((text.match(/([\\d,]+)\\s*円/)||[])[1])||'';
        const remote=/リモート/.test(text); const week=((text.match(/週\\s*([1-5])/)||[])[1])||'';
        let pf=''; for(const p of PREF){{ if(text.includes(p)){{pf=p;break;}} }}
        seen.add(id);
        out.push({{title, url:'https://tech.crowdworks.jp/job_offers/'+id+'/', company:'',
          rate_text: rate?rate+'円/月':'', work_style:(remote?'リモート ':'')+(week?'週'+week:''),
          location:pf, description:title}});
        if(out.length>=40) break;
      }}
      return out;
    }}
    """,
    # フリーランスボード
    "freelance_board": f"""
    () => {{
      const PREF={_PREF_JS}; const out=[]; const seen=new Set();
      for (const a of document.querySelectorAll('a[href*="/jobs/detail/"]')) {{
        const m=a.getAttribute('href').match(/detail\\/(\\d+)/); if(!m) continue;
        const id=m[1]; if(seen.has(id)) continue;
        let card=a; for(let i=0;i<9&&card.parentElement;i++){{card=card.parentElement; if((card.innerText||'').match(/万円|円/)) break;}}
        const text=(card.innerText||'').replace(/\\s+/g,' ').trim(); if(text.length<20) continue;
        let title=(a.innerText||'').replace(/\\s+/g,' ').trim(); if(title.length<6) title=text.slice(0,50);
        title=title.slice(0,70);
        let rate=''; const mm=text.match(/(\\d{{2,4}})\\s*-\\s*(\\d{{2,4}})\\s*万円/)||text.match(/(\\d{{2,4}})\\s*万円/);
        if(mm) rate=(mm[2]||mm[1])+'万円/月';
        const remote=/フルリモート|リモート可|リモート/.test(text); const week=((text.match(/週\\s*([1-5])/)||[])[1])||'';
        let pf=''; for(const p of PREF){{ if(text.includes(p)){{pf=p;break;}} }}
        seen.add(id);
        out.push({{title, url:'https://freelance-board.com/jobs/detail/'+id, company:'',
          rate_text: rate, work_style:(remote?'リモート ':'')+(week?'週'+week:''),
          location:pf, description:title}});
        if(out.length>=40) break;
      }}
      return out;
    }}
    """,
    # ランサーズ（サーバー描画。汎用に近い抽出）
    "lancers": f"""
    () => {{
      const PREF={_PREF_JS}; const out=[]; const seen=new Set();
      for (const a of document.querySelectorAll('a[href*="/work/detail/"], a[href*="/work/"]')) {{
        const h=a.getAttribute('href')||''; const m=h.match(/(\\d{{4,}})/); if(!m) continue;
        const id=m[1]; if(seen.has(id)) continue;
        let card=a; for(let i=0;i<8&&card.parentElement;i++){{card=card.parentElement; if((card.innerText||'').match(/[\\d,]+\\s*円/)) break;}}
        const text=(card.innerText||'').replace(/\\s+/g,' ').trim(); if(text.length<15) continue;
        let title=(a.textContent||'').trim().slice(0,70); if(title.length<6) continue;
        const rate=((text.match(/([\\d,]+)\\s*円/)||[])[1])||'';
        const remote=/リモート|在宅/.test(text);
        let pf=''; for(const p of PREF){{ if(text.includes(p)){{pf=p;break;}} }}
        seen.add(id);
        out.push({{title, url: h.startsWith('http')?h:'https://www.lancers.jp'+h, company:'',
          rate_text: rate?rate+'円':'', work_style:(remote?'リモート':''), location:pf, description:title}});
        if(out.length>=40) break;
      }}
      return out;
    }}
    """,
}

# スクロールが必要なサイト（遅延ロード）
_NEEDS_SCROLL = {"findy", "freelance_board", "crowdworks_tech"}


def _is_playwright_available() -> bool:
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


def fetch_with_browser(
    sources: list[Source],
    keywords: list[str],
    headless: bool = True,
    wait_ms: int = 3500,
    on_log=None,
) -> dict[str, list[Job]]:
    """各サイトをブラウザで開いて案件を取得。{source_key: [Job,...]} を返す。"""
    from playwright.sync_api import sync_playwright

    def log(msg: str):
        if on_log:
            on_log(msg)

    results: dict[str, list[Job]] = {}
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=headless,
            viewport={"width": 1280, "height": 1600},
            locale="ja-JP",
        )
        page = ctx.new_page()
        for s in sources:
            ext = _EXTRACTORS.get(s.key)
            if not ext:
                results[s.key] = []
                log(f"{s.name}: 抽出未対応")
                continue
            url = s.build_search(keywords)
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(wait_ms)
                if s.key in _NEEDS_SCROLL:
                    for _ in range(3):
                        page.mouse.wheel(0, 2500)
                        page.wait_for_timeout(1200)
                records = page.evaluate(ext)
            except Exception as e:  # noqa: BLE001
                results[s.key] = []
                log(f"{s.name}: 取得失敗 {type(e).__name__}: {e}")
                continue
            jobs = norm.from_records(s.key, records or [], fetched_via="browser")
            results[s.key] = jobs
            log(f"{s.name}: {len(jobs)}件")
            time.sleep(0.5)
        ctx.close()
    return results


def open_for_login(keys: Optional[list[str]] = None) -> None:
    """画面ありでブラウザを開き、対象サイトのログインページを表示してユーザー操作を待つ。"""
    from playwright.sync_api import sync_playwright

    login_urls = {
        "levtech": "https://freelance.levtech.jp/",
        "findy": "https://freelance.findy-code.io/",
        "freelance_hub": "https://freelance-hub.jp/",
    }
    keys = keys or ["levtech", "findy"]
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR), headless=False,
            viewport={"width": 1280, "height": 1000}, locale="ja-JP",
        )
        for k in keys:
            if k in login_urls:
                pg = ctx.new_page()
                pg.goto(login_urls[k], wait_until="domcontentloaded")
        print("各タブでログインしてください。完了したら、このターミナルで Enter を押すと閉じます。")
        try:
            input()
        except EOFError:
            pass
        ctx.close()
