"""
静态站点生成器
"""
import os
import re
import json
import shutil
import logging
from datetime import datetime
from typing import Dict, List, Any
import yaml
from jinja2 import Environment, FileSystemLoader

from ..utils import ensure_dir, now_hk

logger = logging.getLogger(__name__)

WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

# 热门地区（用于首页侧栏，值为匹配关键词，不区分大小写）
REGION_KEYWORDS = {
    "中国": ["中国", "china"],
    "中东": ["中东", "middle east", "israel", "巴勒斯坦", "palestin", "syria", "egypt", "iran", "lebanon"],
    "北美": ["北美", "north america", "united states", "canada", "美国", "加拿大"],
    "欧洲": ["欧洲", "europe", "uk", "britain", "germany", "france", "vatican", "梵蒂冈"],
    "非洲": ["非洲", "africa", "nigeria", "egypt", "kenya"],
    "拉美": ["拉美", "latin", "brazil", "mexico", "阿根廷", "哥伦比亚"],
    "亚洲": ["亚洲", "asia", "india", "korea", "韩国", "japan", "日本", "东南亚"],
    "全球": ["全球", "global", "world", "international"],
}

# 热门主题（用于首页侧栏）
TOPIC_KEYWORDS = {
    "宣教": ["宣教", "mission", "missionary"],
    "逼迫": ["逼迫", "persecut", "宗教自由", "religious freedom"],
    "合一": ["合一", "ecumen", "unity"],
    "圣经翻译": ["圣经翻译", "bible translation", "wycliffe"],
    "青年": ["青年", "youth", "student"],
    "植堂": ["植堂", "church plant", "planting"],
    "神学教育": ["神学院", "seminary", "theology"],
    "慈善关怀": ["慈善", "赈灾", "援助", "relief", "charity", "poverty"],
}


def _match_keyword(text: str, kw: str) -> bool:
    """纯 ASCII 关键词按整词匹配，含中文按子串匹配"""
    if all(ord(c) < 128 for c in kw):
        return re.search(r"\b" + re.escape(kw) + r"\b", text) is not None
    return kw in text


def _count_groups(articles: List[Dict[str, Any]], groups: Dict[str, List[str]], top_n: int) -> List[Dict[str, Any]]:
    """统计每个关键词组命中的文章数，返回前 top_n"""
    counts = {}
    for name, kws in groups.items():
        hit = 0
        for a in articles:
            text = ((a.get("title") or "") + " " + (a.get("summary") or "") + " " + " ".join(a.get("tags") or [])).lower()
            if any(_match_keyword(text, kw.lower()) for kw in kws):
                hit += 1
        if hit > 0:
            rep = next((kw for kw in kws if any(ord(c) > 127 for c in kw)), kws[0])
            counts[name] = {"count": hit, "filter": rep}
    ranked = sorted(counts.items(), key=lambda x: x[1]["count"], reverse=True)[:top_n]
    return [{"name": n, "count": v["count"], "filter": v["filter"]} for n, v in ranked]


CATEGORY_META = {
    "news": {"label": "基督教世界资讯", "icon": "📰"},
    "persecution": {"label": "信仰自由与逼迫", "icon": "🕊"},
    "mission": {"label": "宣教运动", "icon": "🌍"},
    "church": {"label": "教会与机构", "icon": "⛪"},
    "theology": {"label": "神学与合一", "icon": "📖"},
    "heresy": {"label": "异端辨析", "icon": "⚠"},
    "culture": {"label": "文化媒体", "icon": "🎬"},
    "wiki": {"label": "百科背景", "icon": "📚"},
}


class SiteGenerator:
    def __init__(self, db_dir: str, site_dir: str, template_dir: str, sources_config: str = None):
        self.db_dir = db_dir
        self.site_dir = site_dir
        self.template_dir = template_dir
        if sources_config is None:
            sources_config = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(template_dir))),
                "config", "sources.yaml",
            )
        self.sources_config = sources_config
        self.env = Environment(loader=FileSystemLoader(template_dir))
        self.db: Dict[str, Any] = {}
        self._load_db()

    def _load_sources(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.sources_config):
            logger.warning(f"Sources config not found: {self.sources_config}")
            return []
        with open(self.sources_config, "r", encoding="utf-8") as f:
            return yaml.safe_load(f).get("sources", []) or []

    def _load_db(self):
        path = os.path.join(self.db_dir, "articles.json")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                self.db = json.load(f)
        else:
            self.db = {"articles": [], "categories": {}, "regions": {}, "sources": {}, "updated_at": now_hk()}

    def _copy_assets(self):
        static_dir = os.path.join(os.path.dirname(self.site_dir), "static")
        if os.path.exists(static_dir):
            shutil.copytree(static_dir, self.site_dir, dirs_exist_ok=True)
            return
        src_assets = os.path.join(self.site_dir, "assets")
        dst_assets = os.path.join(self.site_dir, "assets")
        if src_assets != dst_assets and os.path.exists(src_assets):
            shutil.copytree(src_assets, dst_assets, dirs_exist_ok=True)

    @staticmethod
    def _article_date(a: Dict[str, Any]) -> str:
        date = (a.get("published") or "")[:10]
        if not date or date == "None":
            date = (a.get("fetched_at") or "")[:10]
        return date

    def _build_date_groups(self, articles: List[Dict[str, Any]], limit_days: int = 30) -> Dict[str, List[Dict[str, Any]]]:
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for a in articles:
            date = self._article_date(a)
            if len(date) != 10:
                continue
            groups.setdefault(date, []).append(a)

        ordered: Dict[str, List[Dict[str, Any]]] = {}
        for date in sorted(groups.keys(), reverse=True)[:limit_days]:
            items = groups[date]
            cat_order = {k: i for i, k in enumerate(CATEGORY_META.keys())}
            items.sort(key=lambda x: (cat_order.get(x.get("category", ""), 99), x.get("source", "")))
            ordered[date] = items
        return ordered

    @staticmethod
    def _date_weekday(dates: List[str]) -> Dict[str, str]:
        result = {}
        for date in dates:
            try:
                dt = datetime.strptime(date, "%Y-%m-%d")
                result[date] = WEEKDAY_CN[dt.weekday()]
            except ValueError:
                result[date] = ""
        return result

    def generate(self):
        """生成完整静态站点"""
        ensure_dir(self.site_dir)
        ensure_dir(os.path.join(self.site_dir, "categories"))
        self._copy_assets()

        articles = self.db.get("articles", [])
        categories_count = self.db.get("categories", {})
        sources_count = self.db.get("sources", {})
        regions_count = self.db.get("regions", {})
        updated_at = self.db.get("updated_at", now_hk())

        categories = {}
        for key, meta in CATEGORY_META.items():
            categories[key] = {
                "key": key,
                "label": meta["label"],
                "icon": meta["icon"],
                "count": categories_count.get(key, 0),
            }

        index_tpl = self.env.get_template("index.html")
        date_groups = self._build_date_groups(articles)
        available_dates = sorted(date_groups.keys(), reverse=True)
        calendar_data = {
            "available_dates": available_dates,
            "latest_date": available_dates[0] if available_dates else "",
        }
        html = index_tpl.render(
            root="",
            total=len(articles),
            source_count=len(sources_count),
            categories=categories,
            category_labels={k: v["label"] for k, v in CATEGORY_META.items()},
            date_groups=date_groups,
            date_weekday=self._date_weekday(list(date_groups.keys())),
            calendar_data=calendar_data,
            hot_regions=_count_groups(articles, REGION_KEYWORDS, 8),
            hot_topics=_count_groups(articles, TOPIC_KEYWORDS, 8),
            updated_at=updated_at,
        )
        with open(os.path.join(self.site_dir, "index.html"), "w", encoding="utf-8") as f:
            f.write(html)

        cat_tpl = self.env.get_template("category.html")
        for key, meta in CATEGORY_META.items():
            cat_articles = [a for a in articles if a.get("category") == key]
            cat_articles.sort(key=lambda x: self._article_date(x), reverse=True)
            sources = sorted({a.get("source", "") for a in cat_articles})
            html = cat_tpl.render(
                root="../",
                key=key,
                label=meta["label"],
                icon=meta["icon"],
                count=len(cat_articles),
                sources=sources,
                articles=cat_articles,
                updated_at=updated_at,
                total=len(articles),
            )
            with open(os.path.join(self.site_dir, "categories", f"{key}.html"), "w", encoding="utf-8") as f:
                f.write(html)

        sources = self._load_sources()
        by_cat: Dict[str, List[Dict[str, Any]]] = {}
        for s in sources:
            by_cat.setdefault(s.get("category", "news"), []).append(s)
        src_tpl = self.env.get_template("sources.html")
        html = src_tpl.render(
            root="",
            total=len(sources),
            by_cat=by_cat,
            category_labels={k: v["label"] for k, v in CATEGORY_META.items()},
            category_icons={k: v["icon"] for k, v in CATEGORY_META.items()},
            updated_at=updated_at,
            total_articles=len(articles),
        )
        with open(os.path.join(self.site_dir, "sources.html"), "w", encoding="utf-8") as f:
            f.write(html)

        logger.info(f"Site generated at {self.site_dir}: {len(articles)} articles, {len(categories)} categories, {len(sources)} sources")
