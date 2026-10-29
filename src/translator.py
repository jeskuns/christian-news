"""
英文标题自动翻译（免费接口 + 本地缓存）

提供者顺序：MyMemory（免密钥，实测可用）→ Google 非官方端点（备用）
翻译失败一律返回空字符串，调用方保留原标题，绝不阻塞采集流程。
"""
import os
import re
import json
import time
import logging
from typing import Dict, List

import requests

from .models import Article
from .utils import ensure_dir

logger = logging.getLogger(__name__)

# 判断文本是否已含中文
CJK_RE = re.compile(r"[\u4e00-\u9fff]")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

MYMEMORY_API = "https://api.mymemory.translated.net/get"
GOOGLE_API = "https://translate.googleapis.com/translate_a/single"


class Translator:
    """英文标题转中文，带磁盘缓存避免重复请求"""

    def __init__(self, cache_path: str, timeout: int = 12, delay: float = 0.25):
        self.cache_path = cache_path
        self.timeout = timeout
        self.delay = delay
        self.cache: Dict[str, str] = {}
        self._load_cache()

    def _load_cache(self):
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    self.cache = json.load(f) or {}
            except Exception as e:
                logger.warning(f"加载翻译缓存失败，将重建: {e}")
                self.cache = {}

    def save_cache(self):
        try:
            ensure_dir(os.path.dirname(self.cache_path))
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=1, sort_keys=True)
        except Exception as e:
            logger.warning(f"保存翻译缓存失败: {e}")

    # ---------- 翻译提供者 ----------
    def _mymemory(self, text: str, src: str) -> str:
        resp = requests.get(
            MYMEMORY_API,
            params={"q": text, "langpair": f"{src}|zh-CN"},
            headers={"User-Agent": UA},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        out = ((resp.json().get("responseData") or {}).get("translatedText") or "").strip()
        upper = out.upper()
        if "MYMEMORY WARNING" in upper or "QUOTA" in upper or "INVALID" in upper:
            return ""
        return out

    def _google(self, text: str, src: str) -> str:
        resp = requests.get(
            GOOGLE_API,
            params={"client": "gtx", "sl": src, "tl": "zh-CN", "dt": "t", "q": text},
            headers={"User-Agent": UA},
            timeout=min(self.timeout, 6),
        )
        resp.raise_for_status()
        data = resp.json()
        return "".join(seg[0] for seg in data[0] if seg and seg[0]).strip()

    # ---------- 对外接口 ----------
    def translate(self, text: str, src: str = "en") -> str:
        text = (text or "").strip()
        if not text or CJK_RE.search(text):
            return ""

        key = f"{src}:{text}"
        if key in self.cache:
            return self.cache[key]

        result = ""
        for provider in ("mymemory", "google"):
            try:
                result = getattr(self, f"_{provider}")(text, src)
            except Exception as e:
                logger.debug(f"翻译源 {provider} 失败: {e}")
                result = ""
            if result:
                break
            time.sleep(self.delay)

        if result:
            self.cache[key] = result
        return result

    def translate_articles(self, articles: List[Article], max_items: int = 250) -> int:
        pending = [
            a for a in articles
            if (a.language or "").lower().startswith("en")
            and a.title and not (a.title_zh or "")
        ]
        done = 0
        for a in pending[:max_items]:
            zh = self.translate(a.title, "en")
            if zh:
                a.title_zh = zh
                done += 1
            time.sleep(self.delay)

        self.save_cache()
        logger.info(f"标题翻译完成: {done}/{len(pending)} 条英文标题已转为中文（缓存共 {len(self.cache)} 条）")
        return done
