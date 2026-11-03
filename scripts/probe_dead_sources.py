"""探测第三轮：确定 Premier/Baptist Press 可用地址，验证检索替代方案与 RNS 请求头。用完即删。"""
import re
import time
import feedparser
import requests

PARSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}
FULL_CHROME = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

GOOGLE = "https://news.google.com/rss/search"


def get(url, headers, tries=3, timeout=25):
    for i in range(tries):
        try:
            return requests.get(url, headers=headers, timeout=timeout)
        except Exception as exc:
            if i == tries - 1:
                return exc
            time.sleep(2)


def check(label, url, headers):
    r = get(url, headers)
    if isinstance(r, Exception):
        print(f"  {label:22} ERR {type(r).__name__}: {str(r)[:50]}")
        return
    n = len(feedparser.parse(r.content).entries)
    print(f"  {label:22} {r.status_code} entries={n:<3} {url}")
    if n == 0:
        print(f"      body: {r.text[:200].replace(chr(10), ' ')}")


print("### Religion News Service：两种请求头对比（判断 403 是头还是偶发限流）")
for label, h in (("采集器原头", PARSER_HEADERS), ("完整 Chrome 头", FULL_CHROME)):
    for attempt in range(3):
        check(f"{label} #{attempt+1}", "https://religionnews.com/feed/", h)

print("\n### Baptist Press：feed 正文性质")
for url in ("https://www.baptistpress.com/feed/", "https://www.baptistpress.com/?feed=rss2"):
    check("BP", url, FULL_CHROME)

print("\n### Premier：首页 feed 声明 + 常见路径")
r = get("https://premierchristian.news/", FULL_CHROME)
if isinstance(r, Exception):
    print(f"  homepage ERR {type(r).__name__}")
else:
    print(f"  homepage {r.status_code} {len(r.text)}B")
    for tag in re.findall(r'<link[^>]+rel=["\']alternate["\'][^>]*>', r.text, re.I)[:6]:
        print("  TAG:", tag.strip()[:180])
for url in ("https://premierchristian.news/en/news.rss",
            "https://premierchristian.news/rss/news",
            "https://premierchristian.news/en/rss",
            "https://premierchristian.news/sitemap-news.xml"):
    check("premier", url, FULL_CHROME)

print("\n### 检索替代方案（Google News 按媒体名检索）")
for q, hl, gl, ceid in (("Baptist Press", "en-US", "US", "US|en"),
                        ("Premier Christian News", "en-GB", "GB", "GB|en"),
                        ("Evangelical Focus", "en-US", "US", "US|en"),
                        ("基督教 异端", "zh-CN", "TW", "TW|zh-Hant"),
                        ("成功神学", "zh-CN", "TW", "TW|zh-Hant"),
                        ("新天地 异端", "zh-CN", "TW", "TW|zh-Hant")):
    try:
        resp = requests.get(GOOGLE, params={"q": q, "hl": hl, "gl": gl, "ceid": ceid},
                            headers=FULL_CHROME, timeout=25)
        feed = feedparser.parse(resp.content)
        titles = [e.get("title", "")[:45] for e in feed.entries[:3]]
        print(f"  {resp.status_code} items={len(feed.entries):<4} {ceid:<11} q={q}")
        for t in titles:
            print(f"      - {t}")
    except Exception as exc:
        print(f"  ERR {type(exc).__name__} q={q}")

print("\n### 修正后的候选地址回归验证")
check("CT", "https://www.christianitytoday.com/feed/", FULL_CHROME)
check("CP", "https://www.christianpost.com/rss/", FULL_CHROME)
check("DG", "https://www.desiringgod.org/blog.rss", FULL_CHROME)
