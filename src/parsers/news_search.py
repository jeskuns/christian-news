"""
按关键词检索新闻的解析器（主题/地区动态）

设计目标：解决「众多机构官网 HTML 结构各不相同、generic 选择器全部抓空」的问题。
改用统一的关键词新闻检索，把异构官网变成标准化订阅：

  provider: google   → Google News RSS（覆盖最好，含中文媒体；标准 RSS）
  provider: gdelt    → GDELT DOC API（JSON，长期可用，作为 Google 的自动兜底）

配置写法（sources.yaml）：
  parser: news_search
  extra:
    provider: google
    query: 基督教 宣教
"""
import json
import logging
from datetime import datetime, timezone
from typing import List
from urllib.parse import urlencode

import feedparser
import requests
from bs4 import BeautifulSoup

from ..models import Article, SourceConfig
from ..utils import clean_text, normalize_date

logger = logging.getLogger(__name__)

GOOGLE_NEWS_ENDPOINT = "https://news.google.com/rss/search"
GDELT_ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def parse_news_search(config: SourceConfig) -> List[Article]:
    """按配置里的关键词检索新闻，Google News 优先，GDELT 兜底"""
    extra = config.extra or {}
    query = clean_text(extra.get("query") or config.name)
    if not query:
        logger.warning(f"[{config.name}] news_search 缺少 query")
        return []

    preferred = (extra.get("provider") or "google").lower()
    order = [preferred] + [p for p in ("google", "gdelt") if p != preferred]

    for provider in order:
        try:
            if provider == "google":
                items = _fetch_google(query, config)
            elif provider == "gdelt":
                items = _fetch_gdelt(query, config)
            else:
                continue
        except Exception as e:
            logger.debug(f"[{config.name}] {provider} 检索失败: {e}")
            items = []

        if items:
            logger.info(f"[{config.name}] {provider} 检索到 {len(items)} 条（关键词：{query}）")
            return items
        logger.debug(f"[{config.name}] {provider} 无结果，切换下一个 provider")

    logger.info(f"[{config.name}] 全部 provider 无结果（关键词：{query}）")
    return []


# ---------- Google News RSS ----------

def _fetch_google(query: str, config: SourceConfig) -> List[Article]:
    is_zh = (config.language or "zh").lower().startswith("zh")
    params = {
        "q": query,
        "hl": "zh-CN" if is_zh else "en-US",
        "gl": "CN" if is_zh else "US",
        "ceid": "CN:zh-Hans" if is_zh else "US:en",
    }
    url = f"{GOOGLE_NEWS_ENDPOINT}?{urlencode(params)}"

    resp = requests.get(url, headers={"User-Agent": UA, "Accept": "application/rss+xml,application/xml;q=0.9,*/*;q=0.8"}, timeout=25)
    if resp.status_code != 200:
        return []
    feed = feedparser.parse(resp.content)
    if not feed.entries:
        return []

    articles: List[Article] = []
    for entry in feed.entries[:config.max_items]:
        title = clean_text(entry.get("title", ""))
        link = entry.get("link", "")
        if not title or not link:
            continue

        publisher = ""
        if " - " in title:
            head, tail = title.rsplit(" - ", 1)
            if head and tail:
                title, publisher = head.strip(), tail.strip()

        summary = entry.get("summary", "") or ""
        if summary:
            summary = clean_text(BeautifulSoup(summary, "html.parser").get_text(" "))

        published = normalize_date(entry.get("published", "") or entry.get("updated", ""))
        if not published:
            published = _structured_date(entry)

        articles.append(Article(
            title=title,
            url=link,
            category=config.category,
            source=config.name,
            source_url=config.url,
            published=published or datetime.now(timezone.utc).astimezone().isoformat()[:10],
            summary=summary[:500],
            author=publisher,
            language=config.language,
            country=config.country,
            region=config.region,
            extra={"provider": "google_news", "query": query, "publisher": publisher},
        ))
    return articles


def _structured_date(entry) -> str:
    for key in ("published_parsed", "updated_parsed"):
        value = entry.get(key)
        if value:
            try:
                return datetime(*value[:3]).strftime("%Y-%m-%d")
            except Exception:
                pass
    return ""


# ---------- GDELT DOC API ----------

def _fetch_gdelt(query: str, config: SourceConfig) -> List[Article]:
    params = {
        "query": query,
        "mode": "artlist",
        "format": "json",
        "maxrecords": min(config.max_items * 2, 75),
        "timespan": "30d",
        "sort": "datedesc",
    }
    headers = {"User-Agent": UA, "Accept": "application/json"}
    resp = requests.get(GDELT_ENDPOINT, params=params, headers=headers, timeout=30)
    if resp.status_code != 200 or not resp.text.strip().startswith("{"):
        return []

    data = resp.json()
    articles: List[Article] = []
    for item in data.get("articles", [])[:config.max_items]:
        title = clean_text(item.get("title", ""))
        url = item.get("url", "")
        if not title or not url:
            continue

        articles.append(Article(
            title=title,
            url=url,
            category=config.category,
            source=config.name,
            source_url=config.url,
            published=_gdelt_date(item.get("seendate", "")),
            summary="",
            author=item.get("domain", ""),
            language=config.language,
            country=config.country,
            region=config.region,
            extra={"provider": "gdelt", "query": query, "domain": item.get("domain", "")},
        ))
    return articles


def _gdelt_date(seendate: str) -> str:
    seendate = (seendate or "").strip()
    if len(seendate) >= 8 and seendate[:8].isdigit():
        return f"{seendate[:4]}-{seendate[4:6]}-{seendate[6:8]}"
    return ""
