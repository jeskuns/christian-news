"""
通用工具函数
"""
import re
import os
import json
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
from urllib.parse import urljoin, urlparse


# 香港时区
HK_TZ = timezone(timedelta(hours=8))


def setup_logging(level: int = logging.INFO, log_dir: Optional[str] = None):
    """配置日志"""
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    handlers = [logging.StreamHandler()]
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
        today = datetime.now(HK_TZ).strftime("%Y%m%d")
        handlers.append(logging.FileHandler(os.path.join(log_dir, f"{today}.log"), encoding="utf-8"))
    logging.basicConfig(level=level, format=fmt, handlers=handlers)


def now_hk() -> str:
    return datetime.now(HK_TZ).isoformat()


def today_hk() -> str:
    return datetime.now(HK_TZ).strftime("%Y-%m-%d")


def normalize_date(text: str) -> Optional[str]:
    """从字符串中提取并规范化日期"""
    if not text:
        return None
    text = text.strip()
    # ISO 8601
    m = re.search(r'(\d{4}-\d{2}-\d{2})', text)
    if m:
        return m.group(1)
    # 中文日期
    m = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', text)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    # 美式
    m = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', text)
    if m:
        return f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    return None


def clean_text(text: str) -> str:
    """清理文本空白与特殊字符"""
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


_JUNK_HINTS = [
    "subscribe to", "sign up", "newsletter", "all rights reserved",
    "privacy policy", "cookie", "terms of use", "terms of service",
    "follow us", "share this", "related posts", "you may also like",
    "leave a comment", "previous post", "next post", "download pdf",
    "print this", "in epub", "epub", "mobi", "kindle edition",
    "advertisement", "sponsored", "we use cookies", "©", "(c) ",
]


def normalize_content(text: str) -> str:
    """把抓取到的杂乱正文整理成干净的段落文本（解决逐词断行）。"""
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(ch for ch in text if ch == "\n" or ch >= " ")
    blocks = re.split(r"\n{2,}", text)
    out = []
    for blk in blocks:
        lines = [ln.strip() for ln in blk.split("\n")]
        lines = [ln for ln in lines if ln]
        if not lines:
            continue
        para = re.sub(r"[ \t]+", " ", " ".join(lines)).strip()
        if len(para) < 2:
            continue
        low = para.lower()
        if any(j in low for j in _JUNK_HINTS) and len(para) < 200:
            continue
        out.append(para)
    return "\n\n".join(out)


def make_summary(text: str, n: int = 4) -> str:
    """取正文前 n 个句末标点分割的句子，作为中文导读（新闻默认 4 句）。"""
    if not text:
        return ""
    parts = re.split(r"(?<=[。！？!?；;\.\n])", text)
    parts = [p.strip() for p in parts if p.strip()]
    return " ".join(parts[:n]).strip()


def abs_url(base: str, link: str) -> str:
    """补全相对链接"""
    if not link:
        return ""
    if link.startswith(("http://", "https://")):
        return link
    return urljoin(base, link)


def safe_filename(name: str) -> str:
    """将字符串转换为安全文件名"""
    name = re.sub(r'[^\w\u4e00-\u9fff\-_.]', '_', name)
    return name.strip("_")


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, data: Any, indent: int = 2):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=indent, default=str)


def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def compute_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
