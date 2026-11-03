"""源体检：逐个源给出「当前可用性 / 站点声明的真实 feed / Google News 替代」三档结论。

用法：python scripts/audit_sources.py [limit]
只在 GitHub Actions（美国 IP）上跑才有意义——本机在国内，Google 系与多家外媒会被墙。
"""
import sys
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlparse

import feedparser
import requests
import yaml

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
GOOGLE = "https://news.google.com/rss/search"


def entries_of(url):
    """返回 (状态, 条目数, 首条标题)"""
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code != 200:
            return r.status_code, 0, ""
        feed = feedparser.parse(r.content)
        first = (feed.entries[0].get("title") or "")[:40] if feed.entries else ""
        return 200, len(feed.entries), first
    except Exception as exc:
        return type(exc).__name__, 0, ""


def discover_feeds(base):
    """从站点 HTML 的 <link rel=alternate> 里找出它自己声明的 feed 地址"""
    try:
        import re
        r = requests.get(base, headers=HEADERS, timeout=20)
        found = []
        for tag in re.findall(r'<link[^>]+rel=["\']alternate["\'][^>]*>', r.text, re.I):
            if 'rss' in tag or 'atom' in tag:
                m = re.search(r'href=["\']([^"\']+)', tag, re.I)
                if m:
                    found.append(urljoin(base, m.group(1)))
        return found[:3]
    except Exception:
        return []


def google_alternative(name, language, country):
    hl = "zh-CN" if language == "zh" else "en-US"
    ceid = f"{country}|{'zh-Hant' if language == 'zh' else 'en'}"
    try:
        r = requests.get(GOOGLE, params={"q": f'"{name}"', "hl": hl, "gl": country, "ceid": ceid},
                         headers=HEADERS, timeout=20)
        n = len(feedparser.parse(r.content).entries)
        if n == 0:  # 带引号的精确匹配可能过严，退化为宽匹配
            r = requests.get(GOOGLE, params={"q": name, "hl": hl, "gl": country, "ceid": ceid},
                             headers=HEADERS, timeout=20)
            n = len(feedparser.parse(r.content).entries)
        return n
    except Exception:
        return -1


def audit(source):
    name, url = source.get("name"), source.get("url", "")
    lang, country = source.get("language", "en"), source.get("country", "US")
    parser = source.get("parser", "rss")
    if parser == "news_search":
        q = (source.get("extra") or {}).get("query", name)
        hl = "zh-CN" if lang == "zh" else "en-US"
        ceid = f"{country}|{'zh-Hant' if lang == 'zh' else 'en'}"
        try:
            r = requests.get(GOOGLE, params={"q": q, "hl": hl, "gl": country, "ceid": ceid},
                             headers=HEADERS, timeout=20)
            n = len(feedparser.parse(r.content).entries)
        except Exception as exc:
            n = f"ERR {type(exc).__name__}"
        return f"{name:38} news_search q={q!r} -> {n} 条 (ceid={ceid})"

    if parser not in ("rss", "news_search"):
        return f"{name:38} SKIP 解析器={parser}（非 RSS，脚本不评估）"
    code, n, first = entries_of(url)
    if n:
        return f"{name:38} OK   {n} 条  {url}  | {first}"
    parts = urlparse(url)
    base = f"{parts.scheme}://{parts.netloc}/"
    fixed = []
    for cand in discover_feeds(base):
        c2, n2, _ = entries_of(cand)
        if n2:
            fixed.append(f"{cand}({n2}条)")
    g = google_alternative(name, lang, country)
    return (f"{name:38} BAD  {code} items={n}  {url}\n"
            f"      建议 feed: {', '.join(fixed) if fixed else '未发现'}\n"
            f"      GoogleNews q=\"{name}\" 可获 {g} 条")


docs = yaml.safe_load(open("config/sources.yaml", encoding="utf-8"))
sources = docs["sources"]
if len(sys.argv) > 1:
    sources = sources[:int(sys.argv[1])]
with ThreadPoolExecutor(max_workers=8) as pool:
    for line in pool.map(audit, sources):
        print(line)
print("\n完成")
