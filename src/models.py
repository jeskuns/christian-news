"""
基督教世界新闻知识库数据模型
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, List, Dict, Any
import hashlib
import json


@dataclass
class Article:
    """采集到的新闻条目"""
    title: str
    url: str
    category: str  # news, persecution, mission, church, theology, culture, wiki
    source: str    # 来源名称
    source_url: str
    published: Optional[str] = None
    summary: str = ""
    summary_zh: str = ""  # 英文摘要的中文翻译（失败时为空，页面回退显示原摘要）
    title_zh: str = ""   # 英文标题的中文译名（翻译失败时为空，页面回退显示原标题）
    content: str = ""
    author: str = ""
    tags: List[str] = field(default_factory=list)
    language: str = "zh"  # zh, en, de, ja, etc.
    country: str = "CN"   # CN, US, DE, JP, etc.
    region: str = ""      # 地区维度：中国/中东/北美/欧洲/非洲/拉美/亚洲/全球
    fetched_at: str = field(default_factory=lambda: datetime.now().isoformat())
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def id(self) -> str:
        """基于 URL 和标题生成唯一 ID"""
        key = f"{self.url}|{self.title}".encode("utf-8")
        return hashlib.sha256(key).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self, ensure_ascii: bool = False) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=ensure_ascii, default=str)


@dataclass
class SourceConfig:
    """信息源配置"""
    name: str
    url: str
    category: str
    parser: str        # rss, generic, wikipedia, news_search
    language: str
    country: str
    enabled: bool = True
    selector_title: str = ""
    selector_link: str = ""
    selector_summary: str = ""
    selector_date: str = ""
    selector_items: str = ""
    max_items: int = 20
    region: str = ""
    headers: Dict[str, str] = field(default_factory=dict)
    extra: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SourceConfig":
        # 兼容缺少新字段的配置
        known = {f.name for f in cls.__dataclass_fields__.values()} if False else None
        import dataclasses
        fields = {f.name for f in dataclasses.fields(cls)}
        filtered = {k: v for k, v in d.items() if k in fields}
        return cls(**filtered)


@dataclass
class DailySnapshot:
    """每日采集快照"""
    date: str
    total: int
    categories: Dict[str, int]
    sources: Dict[str, int]
    regions: Dict[str, int]
    errors: List[str]
