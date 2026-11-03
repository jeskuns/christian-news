"""一次性探测脚本：为失效源找出当前可用的 feed 地址 / 检索词。用完即删。"""
import json
import feedparser
import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

RSS_CANDIDATES = {
    "Christianity Today": [
        "https://www.christianitytoday.com/news/rss/",
        "https://www.christianitytoday.com/rss.xml",
        "https://www.christianitytoday.com/feed/",
        "https://feeds.christianitytoday.com/christianitytoday/all",
    ],
    "The Christian Post": [
        "https://www.christianpost.com/rss/full/",
        "https://www.christianpost.com/rss/",
        "https://www.christianpost.com/feed/",
        "https://www.christianpost.com/rss/news.xml",
        "https://feeds.christianpost.com/christianpost/news/",
    ],
    "Religion News Service": [
        "https://religionnews.com/feed/",
        "https://www.religionnews.com/feed/",
        "https://religionnews.com/rss/",
        "https://religionnews.com/feed/?post_type=news",
    ],
    "Premier Christian News": [
        "https://premierchristian.news/rss",
        "https://www.premierchristiannews.com/rss",
        "https://premierchristian.news/en/news/rss",
        "https://premierchristian.news/feed",
        "https://feeds.premierchristiannews.com/premier/news",
    ],
    "Evangelical Focus": [
        "https://evangelicalfocus.com/rss",
        "https://evangelicalfocus.com/feed",
        "https://www.evangelicalfocus.com/rss",
        "https://evangelicalfocus.eu/rss",
        "https://evangelicalfocus.eu/feed",
    ],
    "Baptist Press": [
        "https://www.baptistpress.com/feed/",
        "https://www.baptistpress.com/rss.xml",
        "https://bpnews.net/feed/",
        "https://www.baptistpress.com/v2-feed/",
    ],
    "Desiring God": [
        "https://www.desiringgod.org/feed",
        "https://www.desiringgod.org/feed/",
        "https://www.desiringgod.org/articles.rss",
        "https://www.desiringgod.org/rss.xml",
        "https://www.desiringgod.org/.rss",
    ],
}

SEARCH_CANDIDATES = {
    "异端辨析（中文）": ["异端 邪教 辨析 基督教 辨别", "基督教 异端", "异端 识别 教会", "新天地 异端"],
    "新纪元思潮": ["新纪元 成功神学 异端 辨别", "成功神学", "新纪元运动 教会", "灵恩 偏差 教会"],
}


def probe_rss(name: str, urls: list) -> None:
    print(f"\n### {name}")
    for url in urls:
        try:
            r = requests.get(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, application/xml, text/xml, */*"}, timeout=25)
            feed = feedparser.parse(r.content)
            n = len(feed.entries)
            first = (feed.entries[0].get("title") or "")[:40] if n else ""
            print(f"  {r.status_code} items={n:<3} ct={r.headers.get('content-type','')[:24]:<24} {url}  | {first}")
        except Exception as exc:
            print(f"  ERR {type(exc).__name__}: {str(exc)[:60]} {url}")


def probe_search(name: str, queries: list) -> None:
    print(f"\n### {name} (google_news)")
    for q in queries:
        for hl, ceid in (("zh-CN", "TW|zh-Hant"), ("zh-CN", "CN|zh-CN"), ("en-US", "US|en")):
            try:
                r = requests.get("https://news.google.com/rss/search",
                                 params={"q": q, "hl": hl, "gl": ceid.split("|")[0], "ceid": ceid},
                                 headers={"User-Agent": UA}, timeout=25)
                feed = feedparser.parse(r.content)
                print(f"  {r.status_code} items={len(feed.entries):<3} ceid={ceid:<10} q={q}")
            except Exception as exc:
                print(f"  ERR {type(exc).__name__} ceid={ceid} q={q}")


for src, urls in RSS_CANDIDATES.items():
    probe_rss(src, urls)
for src, qs in SEARCH_CANDIDATES.items():
    probe_search(src, qs)
