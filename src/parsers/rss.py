"""
RSS / Atom 源解析器
"""
import logging
from typing import List
from datetime import datetime
import feedparser
from bs4 import BeautifulSoup

from ..models import Article, SourceConfig
from ..utils import clean_text, normalize_date, abs_url

logger = logging.getLogger(__name__)


def parse_feed(config: SourceConfig) -> List[Article]:
    """解析 RSS/Atom 订阅源"""
    articles = []
    try:
        feed = feedparser.parse(config.url)
    except Exception as e:
        logger.error(f"RSS parse error [{config.name}]: {e}")
        return articles

    for entry in feed.entries[:config.max_items]:
        try:
            title = clean_text(entry.get("title", ""))
            link = entry.get("link", "")
            if not title or not link:
                continue
            summary = clean_text(entry.get("summary", entry.get("description", "")))
            if summary:
                summary = BeautifulSoup(summary, "html.parser").get_text(" ")
            published = entry.get("published", entry.get("updated", ""))
            author = clean_text(entry.get("author", ""))
            tags = [t.term for t in entry.get("tags", []) if hasattr(t, "term")]

            articles.append(Article(
                title=title,
                url=abs_url(config.url, link),
                category=config.category,
                source=config.name,
                source_url=config.url,
                published=normalize_date(published) or datetime.now().isoformat()[:10],
                summary=summary[:500],
                author=author,
                tags=tags,
                language=config.language,
                country=config.country,
                region=config.region,
                extra={"feed_type": feed.version if hasattr(feed, "version") else "unknown"}
            ))
        except Exception as e:
            logger.warning(f"Skip RSS entry in {config.name}: {e}")
            continue
    logger.info(f"[{config.name}] RSS parsed {len(articles)} items")
    return articles
