"""探测第二轮：发现真实 feed 地址 + 验证请求头影响。用完即删。"""
import re
import feedparser
import requests

BROWSER = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
    "Accept-Language": "en-US,en;q=0.9",
}
FEED_ACCEPT = {"Accept": "application/rss+xml, application/xml, text/xml, */*"}

DISCOVER_FROM = {
    "Desiring God": "https://www.desiringgod.org/",
    "Premier Christian News": "https://premierchristian.news/en/news",
    "Baptist Press": "https://www.baptistpress.com/",
    "Evangelical Focus": "https://evangelicalfocus.com/",
}

# 已知返回 200 但 feedparser 解析 0 条：看正文到底是什么
MYSTERY_BODIES = [
    ("Baptist Press", "https://www.baptistpress.com/feed/"),
    ("Christianity Today", "https://www.christianitytoday.com/news/rss/"),
]


def discover(name: str, page_url: str) -> None:
    print(f"\n### {name} — 从 {page_url} 找 feed 链接")
    try:
        r = requests.get(page_url, headers=BROWSER, timeout=30)
        print(f"  homepage {r.status_code} {len(r.text)}B")
        links = re.findall(
            r'<link[^>]+rel=["\']alternate["\'][^>]*>', r.text, re.IGNORECASE)
        for tag in links[:8]:
            print("  TAG:", tag.strip()[:200])
        # 页面上出现的 rss/atom/feed 字样链接
        for href in sorted(set(re.findall(r'href=["\']([^"\']*(?:rss|atom|feed)[^"\']*)["\']', r.text, re.IGNORECASE)))[:12]:
            print("  HREF:", href[:150])
    except Exception as exc:
        print(f"  ERR {type(exc).__name__}: {str(exc)[:80]}")
    # 常见约定路径
    base = page_url.split("/")[0] + "//" + page_url.split("/")[2]
    for path in ("/rss", "/feed", "/rss.xml", "/atom.xml", "/feed.xml", "/api/rss", "/news/feed"):
        url = base + path
        try:
            r = requests.get(url, headers={**BROWSER, **FEED_ACCEPT}, timeout=20)
            n = len(feedparser.parse(r.content).entries)
            if r.status_code != 404 or n:
                print(f"  {r.status_code} items={n:<3} ct={r.headers.get('content-type','')[:26]:<26} {url}")
        except Exception as exc:
            print(f"  ERR {type(exc).__name__:16} {url}")


def body_peek(name: str, url: str) -> None:
    print(f"\n### {name} — 200 但 0 条，看正文前 400 字符")
    for hdrs, label in ((BROWSER, "无 Accept"), ({**BROWSER, **FEED_ACCEPT}, "带 Accept")):
        try:
            r = requests.get(url, headers=hdrs, timeout=25)
            feed = feedparser.parse(r.content)
            print(f"  [{label}] {r.status_code} entries={len(feed.entries)} ct={r.headers.get('content-type','')[:30]}")
            print("   ", r.text[:400].replace("\n", " "))
        except Exception as exc:
            print(f"  [{label}] ERR {type(exc).__name__}: {str(exc)[:60]}")


def header_effect(name: str, url: str) -> None:
    print(f"\n### {name} — 403 是否由请求头决定")
    combos = {
        "仅 UA": {"User-Agent": BROWSER["User-Agent"]},
        "UA+Accept": {**BROWSER, **FEED_ACCEPT},
        "UA+Accept+Referer": {**BROWSER, **FEED_ACCEPT, "Referer": url},
        "UA+Sec-Fetch": {**BROWSER, "Sec-Fetch-Dest": "document", "Sec-Fetch-Mode": "navigate",
                         "Sec-Fetch-Site": "none", "Upgrade-Insecure-Requests": "1"},
        "空 UA": {"User-Agent": ""},
        "feedparser 默认 UA": {"User-Agent": "Feedparser/6.0"},
    }
    for label, hdrs in combos.items():
        try:
            r = requests.get(url, headers=hdrs, timeout=25)
            print(f"  {r.status_code} entries={len(feedparser.parse(r.content).entries):<3} {label}")
        except Exception as exc:
            print(f"  ERR {type(exc).__name__:16} {label}")


for name, url in DISCOVER_FROM.items():
    discover(name, url)
for name, url in MYSTERY_BODIES:
    body_peek(name, url)
header_effect("Religion News Service", "https://religionnews.com/feed/")
header_effect("Evangelical Focus", "https://evangelicalfocus.com/rss")
