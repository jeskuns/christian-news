"""
多源数据采集引擎
"""
import os
import yaml
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib

from .models import Article, SourceConfig, DailySnapshot
from .parsers import parse_feed, parse_generic, parse_wikipedia, parse_news_search
from .utils import ensure_dir, save_json, today_hk, now_hk
from .translator import Translator

logger = logging.getLogger(__name__)

PARSER_MAP = {
    "rss": parse_feed,
    "generic": parse_generic,
    "wikipedia": parse_wikipedia,
    "news_search": parse_news_search,
}

CATEGORY_LABELS = {
    "news": "基督教世界资讯",
    "persecution": "信仰自由与逼迫",
    "mission": "宣教运动",
    "church": "教会与机构",
    "theology": "神学与合一",
    "heresy": "异端辨析",
    "culture": "文化媒体",
    "wiki": "百科背景",
}


class Collector:
    def __init__(self, config_path: str, data_dir: str, workers: int = 8):
        self.config_path = config_path
        self.data_dir = data_dir
        self.raw_dir = os.path.join(data_dir, "raw")
        self.db_dir = os.path.join(data_dir, "db")
        self.workers = workers
        self.sources: List[SourceConfig] = []
        self.articles: List[Article] = []
        self.errors: List[str] = []
        self._load_sources()

    def _load_sources(self):
        with open(self.config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        for item in raw.get("sources", []):
            self.sources.append(SourceConfig.from_dict(item))
        logger.info(f"Loaded {len(self.sources)} sources from {self.config_path}")

    def _collect_one(self, source: SourceConfig) -> List[Article]:
        if not source.enabled:
            return []
        parser = PARSER_MAP.get(source.parser)
        if not parser:
            msg = f"Unknown parser '{source.parser}' for source '{source.name}'"
            logger.error(msg)
            self.errors.append(msg)
            return []
        try:
            articles = parser(source)
            for a in articles:
                a.category = source.category  # 强制按配置分类
                if not a.region:
                    a.region = source.region or ""
            return articles
        except Exception as e:
            msg = f"Source '{source.name}' failed: {e}"
            logger.error(msg)
            self.errors.append(msg)
            return []

    def collect(self) -> List[Article]:
        """并发采集全部启用源"""
        self.articles = []
        self.errors = []
        enabled = [s for s in self.sources if s.enabled]
        logger.info(f"Start collecting from {len(enabled)} sources with {self.workers} workers")

        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            future_to_source = {executor.submit(self._collect_one, s): s for s in enabled}
            for future in as_completed(future_to_source):
                source = future_to_source[future]
                try:
                    items = future.result()
                    self.articles.extend(items)
                    logger.info(f"[{source.name}] collected {len(items)} articles")
                except Exception as e:
                    msg = f"Future error [{source.name}]: {e}"
                    logger.error(msg)
                    self.errors.append(msg)

        # 去重
        seen = set()
        unique = []
        for a in self.articles:
            if a.id not in seen:
                seen.add(a.id)
                unique.append(a)
        self.articles = unique
        logger.info(f"Total unique articles after dedup: {len(self.articles)}")

        # 英文标题自动翻译为中文（带本地缓存；失败则保留原标题）
        translator = Translator(os.path.join(self.data_dir, "translation_cache.json"))
        translator.translate_articles(self.articles)

        return self.articles

    def save_raw(self):
        """保存原始采集结果按日期归档"""
        ensure_dir(self.raw_dir)
        date = today_hk()
        path = os.path.join(self.raw_dir, f"{date}.json")
        data = [a.to_dict() for a in self.articles]
        save_json(path, data)
        logger.info(f"Raw data saved to {path}")

    def build_database(self, retention_days: int = 90, max_articles: int = 8000):
        """构建数据库：与历史数据合并（按 id 去重），并保留最近 retention_days 天"""
        ensure_dir(self.db_dir)
        db_path = os.path.join(self.db_dir, "articles.json")

        merged: Dict[str, Dict[str, Any]] = {}
        if os.path.exists(db_path):
            try:
                with open(db_path, "r", encoding="utf-8") as f:
                    old = json.load(f)
                for a in old.get("articles", []):
                    key = hashlib.sha256(
                        f"{a.get('url','')}|{a.get('title','')}".encode("utf-8")
                    ).hexdigest()[:16]
                    merged[key] = a
            except Exception as e:
                logger.warning(f"读取历史数据库失败，将重建: {e}")

        for a in self.articles:
            merged[a.id] = a.to_dict()

        cutoff = (datetime.now() - timedelta(days=retention_days)).strftime("%Y-%m-%d")
        kept = []
        for a in merged.values():
            date = (a.get("published") or "")[:10] or (a.get("fetched_at") or "")[:10]
            if date and date >= cutoff:
                kept.append(a)
        kept.sort(key=lambda a: ((a.get("published") or a.get("fetched_at") or "")[:10]), reverse=True)
        kept = kept[:max_articles]

        logger.info(
            f"Database merged: {len(self.articles)} new + history -> {len(kept)} kept "
            f"(retention {retention_days}d, cutoff {cutoff})"
        )

        db = {
            "updated_at": now_hk(),
            "total": len(kept),
            "categories": {},
            "regions": {},
            "sources": {},
            "articles": kept,
        }
        for a in kept:
            db["categories"][a["category"]] = db["categories"].get(a["category"], 0) + 1
            if a.get("region"):
                db["regions"][a["region"]] = db["regions"].get(a["region"], 0) + 1
            db["sources"][a["source"]] = db["sources"].get(a["source"], 0) + 1

        save_json(db_path, db)

        for cat in db["categories"]:
            cat_articles = [a for a in kept if a["category"] == cat]
            save_json(os.path.join(self.db_dir, f"{cat}.json"), {
                "category": cat,
                "label": CATEGORY_LABELS.get(cat, cat),
                "count": len(cat_articles),
                "updated_at": now_hk(),
                "articles": cat_articles,
            })
        logger.info("Database built and indexed by category")

    def snapshot(self) -> DailySnapshot:
        """生成每日快照摘要"""
        cats: Dict[str, int] = {}
        srcs: Dict[str, int] = {}
        regs: Dict[str, int] = {}
        for a in self.articles:
            cats[a.category] = cats.get(a.category, 0) + 1
            srcs[a.source] = srcs.get(a.source, 0) + 1
            if a.region:
                regs[a.region] = regs.get(a.region, 0) + 1
        snap = DailySnapshot(
            date=today_hk(),
            total=len(self.articles),
            categories=cats,
            sources=srcs,
            regions=regs,
            errors=self.errors,
        )
        save_json(os.path.join(self.db_dir, "snapshot.json"), snap.__dict__)
        return snap
