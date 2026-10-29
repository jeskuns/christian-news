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

# 来源立场推断：按名称关键词识别与福音派传统不同的来源（用于阅读提示）
STANCE_KEYWORDS = [
    ("catholic", ["天主教", "catholic", "vatican", "asia news"]),
    ("orthodox", ["东正教", "orthodox"]),
    ("mainline", ["卫理公会", "methodist", "圣公会", "anglican", "普世", "ecumenical", "world council", "wcc"]),
    ("charismatic", ["灵恩", "charisma", "pentecostal"]),
    ("academic", ["季刊", "期刊", "journal", "themelios", "first things", "modern reformation",
                  "life quarterly", "建道", "神学研究院", "jets"]),
]

# 争议话题关键词（扫描标题+摘要；命中则加「争议话题」标记）
CONTROVERSY_KEYWORDS = {
    "同性婚姻": ["同性婚姻", "同性恋", "同性婚礼", "gay marriage", "same-sex", "lgbt", "lgbtq", "homosexual"],
    "堕胎": ["堕胎", "abortion", "罗诉韦德", "roe v. wade"],
    "女性按立": ["女性按立", "女牧师", "女性牧者", "women ordination", "female pastor", "女主教"],
    "跨性别": ["跨性别", "变性", "transgender"],
    "成功神学": ["成功神学", "prosperity gospel", "健康财富", "财富福音"],
    "灵恩现象": ["说方言", "圣灵恩赐", "灵恩", "charismatic", "speaking in tongues"],
    "圣经权威": ["圣经无误", "圣经权威", "inerrancy"],
    "创造与进化": ["进化论", "创造论", "evolution", "creationism"],
}

# 需向读者提示「立场不同于福音派」的传统
FLAGGED_STANCES = {"catholic", "orthodox", "mainline"}


def infer_stance(source: "SourceConfig") -> str:
    """按来源名称关键词推断其神学传统；默认福音派"""
    name = (source.name or "").lower()
    for stance, kws in STANCE_KEYWORDS:
        for kw in kws:
            if kw in name:
                return stance
    return "evangelical"


# 精选优先级：权威/常看福音派媒体排高；聚合类（Google News 搜索）与百科背景排低
PRIORITY_HIGH = [
    "gospel coalition", "9marks", "desiring god", "christianity today", "crossway",
    "ligonier", "monergism", "banner of truth", "witherspoon", "first things",
    "modern reformation", "themelios", "lifeway", "got questions", "answers in genesis",
    "persecution", "opendoors", "uscirf",
]


def infer_priority(source: "SourceConfig") -> int:
    """按来源类型/名称推断精选优先级：3=高、2=中、1=低"""
    if source.parser == "news_search":
        return 1  # Google News 聚合结果（多为重复）
    if (source.category or "") == "wiki":
        return 1  # 百科背景非时效性新闻
    name = (source.name or "").lower()
    if any(kw in name for kw in PRIORITY_HIGH):
        return 3
    return 2


def flag_articles(articles: List[Article]) -> None:
    """扫描标题+摘要，为涉及争议公共议题的条目打上标记（上限 3 个）"""
    for a in articles:
        text = " ".join([a.title or "", a.summary or "", a.summary_zh or ""]).lower()
        fl = []
        for label, kws in CONTROVERSY_KEYWORDS.items():
            if any(kw.lower() in text for kw in kws):
                fl.append(label)
        a.flags = fl[:3]


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
                a.stance = source.stance or infer_stance(source)
                a.priority = source.priority or infer_priority(source)
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

        # 为涉及争议公共议题的条目打标记（福音派视角阅读提示）
        flag_articles(self.articles)

        return self.articles

    def save_raw(self):
        """保存原始采集结果按日期归档"""
        ensure_dir(self.raw_dir)
        date = today_hk()
        path = os.path.join(self.raw_dir, f"{date}.json")
        data = [a.to_dict() for a in self.articles]
        save_json(path, data)
        logger.info(f"Raw data saved to {path}")

    def _select_featured(self, articles: List[Dict[str, Any]], limit: int = 250) -> List[Dict[str, Any]]:
        """精选：优先级高、更新鲜的优先；并保证各分类都有基本覆盖"""
        ordered = sorted(
            articles,
            key=lambda a: (
                a.get("priority", 2),
                (a.get("published") or a.get("fetched_at") or "")[:10],
            ),
            reverse=True,
        )
        cats: Dict[str, List[Dict[str, Any]]] = {}
        for a in ordered:
            cats.setdefault(a.get("category", ""), []).append(a)
        ncat = len(cats)
        if ncat == 0:
            return ordered[:limit]
        min_per = max(3, limit // ncat)
        picked: List[Dict[str, Any]] = []
        picked_ids = set()
        for items in cats.values():
            for a in items[:min_per]:
                picked.append(a)
                picked_ids.add(a.get("id"))
        for a in ordered:
            if len(picked) >= limit:
                break
            if a.get("id") not in picked_ids:
                picked.append(a)
                picked_ids.add(a.get("id"))
        return picked[:limit]

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

        # 精选：按「优先级 + 新鲜度 + 分类均衡」筛选 limit 条，供首页/分类页展示
        featured = self._select_featured(kept, limit=250)

        logger.info(
            f"Database merged: {len(self.articles)} new + history -> {len(kept)} kept "
            f"(retention {retention_days}d, cutoff {cutoff})"
        )

        db = {
            "updated_at": now_hk(),
            "total": len(kept),
            "featured_count": len(featured),
            "categories": {},
            "regions": {},
            "sources": {},
            "articles": kept,
            "featured": featured,
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
