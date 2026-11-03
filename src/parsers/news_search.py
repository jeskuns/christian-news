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
import re
import threading
import time
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

# GDELT DOC API 对每个 IP 限速「5 秒 1 次」，超出的请求返回一行纯文本提示而不是 JSON。
# 采集器用 8 线程并发，所以在持锁状态下强制间隔：否则 provider: gdelt 的源基本全抓空。
_GDELT_MIN_INTERVAL = 5.0
_GDELT_LOCK = threading.Lock()
_GDELT_LAST = [0.0]


def _gdelt_slot() -> None:
    with _GDELT_LOCK:
        wait = _GDELT_MIN_INTERVAL - (time.monotonic() - _GDELT_LAST[0])
        if wait > 0:
            time.sleep(wait)
        _GDELT_LAST[0] = time.monotonic()


UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


def parse_news_search(config: SourceConfig) -> List[Article]:
    """按配置里的关键词检索新闻，Google News 优先，GDELT 兜底"""
    extra = config.extra or {}
    query = clean_text(extra.get("query") or config.name)
    if not query:
        logger.warning(f"[{config.name}] news_search 缺少 query")
        return []

    preferred = (extra.get("provider") or "google").lower()
    order = [preferred] + [p for p in ("google", "gdelt") if p != preferred]
    ladder = _relax_ladder(query)

    for provider in order:
        if provider not in ("google", "gdelt"):
            continue
        for q in ladder:
            try:
                if provider == "google":
                    items = _fetch_google(q, config)
                else:
                    items = _fetch_gdelt(q, config)
            except Exception as e:
                logger.debug(f"[{config.name}] {provider} 检索失败: {e}")
                items = []

            if items:
                note = "" if q == query else f"，原词 {query!r} 过窄已放宽"
                logger.info(f"[{config.name}] {provider} 检索到 {len(items)} 条（关键词：{q}{note}）")
                return items
        logger.debug(f"[{config.name}] {provider} 无结果，切换下一个 provider")

    logger.info(f"[{config.name}] 全部 provider 无结果（关键词：{query}）")
    return []


def _relax_ladder(query: str) -> List[str]:
    """Google News 把空格当 AND，词一多就 0 条；逐级去掉尾部词，保留前两词为主旨"""
    terms = query.split()
    if len(terms) < 3:
        return [query]
    ladder = [query] + [" ".join(terms[:n]) for n in range(len(terms) - 1, 1, -1)]
    seen, out = set(), []
    for q in ladder:
        # 去掉尾部词可能把 OR/AND 孤零零留在句尾，那是无效查询
        if q in seen or re.search(r"\b(OR|AND)$", q, re.IGNORECASE):
            continue
        seen.add(q)
        out.append(q)
    return out


# ---------- Google News RSS ----------

def _google_locale_variants(config: SourceConfig) -> List[dict]:
    """按配置的 country/language 给出 Google News 版位参数候选。

    gl 决定返回哪个地区版、hl 决定检索语言、ceid 是「地区:文字」。原实现只按语言
    回落到 CN/US 两个版位，配置里写 TW/HK/SG/JP/KR 也照样抓回大陆版或美版结果，
    东亚与东南亚的源因此出不来。若某个「地区:文字」组合 Google 不认（空 feed），
    再退回按语言的通用版位，保证老源不会因参数变化而丢结果。
    """
    country = (config.country or "").strip().upper() or "US"
    lang = (config.language or "en").strip().lower().split("-")[0]
    traditional = ("TW", "HK", "MO", "MY")
    if lang == "zh":
        hl = {"TW": "zh-TW", "HK": "zh-HK", "MO": "zh-MO", "MY": "zh-TW"}.get(country, "zh-CN")
        script = "zh-Hant" if country in traditional else "zh-Hans"
    else:
        hl = {"ja": "ja", "ko": "ko", "id": "id"}.get(lang, "en-US")
        script = {"ja": "ja", "ko": "ko", "id": "id"}.get(lang, "en")

    exact = {"hl": hl, "gl": country, "ceid": f"{country}:{script}"}
    generic = {
        "hl": "zh-CN" if lang == "zh" else "en-US",
        "gl": "CN" if lang == "zh" else "US",
        "ceid": "CN:zh-Hans" if lang == "zh" else "US:en",
    }
    return [exact] if exact == generic else [exact, generic]


def _fetch_google(query: str, config: SourceConfig) -> List[Article]:
    entries = []
    for locale in _google_locale_variants(config):
        params = {"q": query}
        params.update(locale)
        url = f"{GOOGLE_NEWS_ENDPOINT}?{urlencode(params)}"
        try:
            resp = requests.get(url, headers={"User-Agent": UA, "Accept": "application/rss+xml,application/xml;q=0.9,*/*;q=0.8"}, timeout=25)
        except Exception as exc:
            logger.debug(f"[{config.name}] google_news {locale['ceid']} 请求失败: {exc}")
            continue
        if resp.status_code != 200:
            continue
        parsed = feedparser.parse(resp.content)
        if parsed.entries:
            entries = parsed.entries[:config.max_items]
            break

    if not entries:
        return []

    articles: List[Article] = []
    for entry in entries:
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
    _gdelt_slot()
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
