"""
通用网页解析器（基于 CSS 选择器）
"""
import logging
import requests
from datetime import datetime
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from typing import List

from ..models import Article, SourceConfig
from ..utils import clean_text, normalize_date, abs_url

logger = logging.getLogger(__name__)
ua = UserAgent(fallback="Mozilla/5.0 (Windows NT 10.0; Win64; x64)")


def parse_generic(config: SourceConfig) -> List[Article]:
    """基于配置选择器抓取通用网页列表"""
    articles = []
    if not config.selector_items:
        logger.warning(f"[{config.name}] missing selector_items")
        return articles

    headers = {
        "User-Agent": ua.random,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    headers.update(config.headers)

    try:
        resp = requests.get(config.url, headers=headers, timeout=30)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
    except Exception as e:
        logger.error(f"Fetch error [{config.name}]: {e}")
        return articles

    soup = BeautifulSoup(resp.text, "html.parser")
    items = soup.select(config.selector_items)

    for item in items[:config.max_items]:
        try:
            title_el = item.select_one(config.selector_title) or item
            link_el = item.select_one(config.selector_link) or item
            summary_el = item.select_one(config.selector_summary) if config.selector_summary else None
            date_el = item.select_one(config.selector_date) if config.selector_date else None

            title = clean_text(title_el.get_text())
            link = link_el.get("href", "")
            if not title or not link:
                continue

            summary = clean_text(summary_el.get_text()) if summary_el else ""
            published = normalize_date(date_el.get_text()) if date_el else None

            articles.append(Article(
                title=title,
                url=abs_url(config.url, link),
                category=config.category,
                source=config.name,
                source_url=config.url,
                published=published or datetime.now().isoformat()[:10],
                summary=summary[:500],
                language=config.language,
                country=config.country,
                region=config.region,
            ))
        except Exception as e:
            logger.warning(f"Skip generic item in {config.name}: {e}")
            continue
    logger.info(f"[{config.name}] Generic parsed {len(articles)} items")
    return articles
