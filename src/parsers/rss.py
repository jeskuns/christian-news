"""
RSS / Atom 源解析器
"""
import logging
import re
from typing import List
from datetime import datetime
import feedparser
from bs4 import BeautifulSoup

from ..models import Article, SourceConfig
from ..utils import clean_text, normalize_date, abs_url, normalize_content

try:
    from .extract import extract_article
except Exception:
    extract_article = None

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

            # 优先取 feeds 自带全文（content:encoded），否则兜底抓原页，用于生成 3-5 句中文摘要
            content = ""
            raw_html = ""
            for blk in (entry.get("content") or []):
                if isinstance(blk, dict) and blk.get("value"):
                    raw_html += blk["value"] + "\n"
            if raw_html:
                content = normalize_content(BeautifulSoup(raw_html, "html.parser").get_text("\n", strip=True))[:8000]
            if not content and link and re.match(r'^https?://', link) and extract_article:
                try:
                    pc = extract_article(abs_url(config.url, link), config.language if config.language in ("zh",) else "en")
                    if pc and len(pc) > len(summary or "x"):
                        content = normalize_content(pc)[:8000]
                except Exception as e:
                    logger.debug(f"正文抓取失败 [{config.name}]: {e}")

            articles.append(Article(
                title=title,
                url=abs_url(config.url, link),
                category=config.category,
                source=config.name,
                source_url=config.url,
                published=normalize_date(published) or datetime.now().isoformat()[:10],
                summary=summary[:500],
                content=content,
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
