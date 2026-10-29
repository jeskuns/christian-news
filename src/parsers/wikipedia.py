"""
Wikipedia 基督教相关条目解析
"""
import logging
import requests
from datetime import datetime
from typing import List
from urllib.parse import quote

from ..models import Article, SourceConfig
from ..utils import clean_text

logger = logging.getLogger(__name__)

# 基督教主题关键词（用于检索百科背景条目）
CHRISTIAN_KEYWORDS = [
    "Christianity", "Protestantism", "Catholic Church", "Eastern Orthodox Church",
    "Bible", "Gospel", "Missionary", "Persecution of Christians",
    "Ecumenism", "Christian theology", "Pentecostalism", "Evangelicalism",
    "基督教", "新教", "天主教", "东正教", "圣经", "福音", "宣教",
    "教会", "神学", "基督教 persecution", "合一运动", "五旬节派"
]


def parse_wikipedia(config: SourceConfig) -> List[Article]:
    """从 MediaWiki API（Wikipedia 或兼容站点）获取基督教相关近期更新条目"""
    articles = []
    lang = config.language or "en"
    base = config.url.rstrip("/") if config.url else f"https://{lang}.wikipedia.org/w/api.php"
    ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/120.0 Safari/537.36") if "wikipedia.org" not in base \
        else "ChristianNewsKB/1.0 (research bot)"
    headers = {"User-Agent": ua}

    try:
        api_host = base.split("/w/api.php")[0] if "/w/api.php" in base else f"https://{lang}.wikipedia.org"
        wiki_base = f"{api_host}/wiki/"
        for keyword in CHRISTIAN_KEYWORDS[:5]:
            params = {
                "action": "query",
                "list": "search",
                "srsearch": keyword,
                "srlimit": config.max_items // 5 or 3,
                "format": "json",
                "origin": "*"
            }
            resp = requests.get(base, params=params, headers=headers, timeout=30)
            data = resp.json()
            for item in data.get("query", {}).get("search", []):
                title = clean_text(item.get("title", ""))
                if not title:
                    continue
                articles.append(Article(
                    title=title,
                    url=f"{wiki_base}{quote(title.replace(' ', '_'))}",
                    category="wiki",
                    source=f"Wikipedia ({lang})",
                    source_url=base,
                    published=datetime.now().isoformat()[:10],
                    summary=clean_text(item.get("snippet", "")).replace("<span class=\"searchmatch\">", "").replace("</span>", ""),
                    language=lang,
                    country=config.country,
                    region=config.region,
                    extra={"wordcount": item.get("wordcount")}
                ))
    except Exception as e:
        logger.error(f"Wikipedia parse error [{config.name}]: {e}")
    logger.info(f"[{config.name}] Wikipedia parsed {len(articles)} items")
    return articles
