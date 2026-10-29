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

    def __init__(self, cache_path: str, timeout: int = 12, delay: float = 0.1, use_offline: bool = True):
        self.cache_path = cache_path
        self.timeout = timeout
        self.delay = delay
        self.use_offline = use_offline
        self.cache: Dict[str, str] = {}
        self._argos = None
        self._argos_ready = False
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

        # 云端配额用尽或失败时，回退本地离线翻译（不限量、无密钥）
        if not result and self.use_offline:
            result = self._argos_translate(text, src)

        if result:
            self.cache[key] = result
        return result

    # ---------- 离线翻译（argos-translate，本地运行、无配额） ----------
    def _pip_install_argos(self) -> bool:
        """按需安装离线翻译库（仅当云端配额用尽时触发，平时不装，保持运行轻量）"""
        import subprocess
        import sys
        logger.info("云端翻译配额用尽，按需安装离线翻译库 argostranslate（仅此一次，较重）…")
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "--no-cache-dir", "argostranslate"]
            )
            return True
        except Exception as e:
            logger.warning(f"pip 安装 argostranslate 失败: {e}")
            return False

    def _get_argos(self):
        if not self.use_offline or self._argos_ready:
            return self._argos
        self._argos_ready = True
        try:
            import argostranslate.package as argos_pkg
            import argostranslate.translate as argos_tr
        except ImportError:
            # 运行时按需安装（仅在云端配额用尽时触发，避免每次运行都装重型依赖）
            if self._pip_install_argos():
                try:
                    import argostranslate.package as argos_pkg
                    import argostranslate.translate as argos_tr
                except Exception as e:
                    logger.warning(f"argos 安装后仍无法导入，放弃离线翻译: {e}")
                    self._argos = None
                    return None
            else:
                self._argos = None
                return None

        try:
            from_code, to_code = "en", "zh"
            installed = argos_tr.get_installed_languages()
            translation = None
            try:
                src_lang = next(l for l in installed if l.code == from_code)
                tgt_lang = next(l for l in installed if l.code == to_code)
                translation = src_lang.get_translation(tgt_lang)
            except Exception:
                translation = None
            if translation is None:
                logger.info("未找到本地 en->zh 翻译模型，尝试下载（约数十 MB）…")
                argos_pkg.update_package_index()
                available = argos_pkg.get_available_packages()
                pkg = next((p for p in available
                            if p.from_code == from_code and p.to_code == to_code), None)
                if pkg is None:
                    raise RuntimeError("argos 未提供 en->zh 模型")
                argos_pkg.install_package(pkg)
                installed = argos_tr.get_installed_languages()
                src_lang = next(l for l in installed if l.code == from_code)
                tgt_lang = next(l for l in installed if l.code == to_code)
                translation = src_lang.get_translation(tgt_lang)
            self._argos = (src_lang, tgt_lang, translation)
            logger.info("argos 离线翻译就绪（en->zh）")
            return self._argos
        except Exception as e:
            logger.warning(f"argos 离线翻译不可用，将仅使用云端翻译: {e}")
            self._argos = None
            return None

    def _argos_translate(self, text: str, src: str) -> str:
        if src != "en":
            return ""  # 仅内置 en->zh 模型
        m = self._get_argos()
        if not m:
            return ""
        _, _, translation = m
        try:
            return (translation.translate(text) or "").strip()
        except Exception as e:
            logger.debug(f"argos 翻译失败: {e}")
            return ""

    def translate_articles(self, articles: List[Article], max_items: int = None) -> int:
        title_pending = [
            a for a in articles
            if (a.language or "").lower().startswith("en")
            and a.title and not (a.title_zh or "")
        ]
        summary_pending = [
            a for a in articles
            if (a.language or "").lower().startswith("en")
            and a.summary and not (a.summary_zh or "")
        ]
        tlist = title_pending if max_items is None else title_pending[:max_items]
        slist = summary_pending if max_items is None else summary_pending[:max_items]
        done = 0
        for a in tlist:
            zh = self.translate(a.title, "en")
            if zh:
                a.title_zh = zh
                done += 1
            time.sleep(self.delay)

        sdone = 0
        for a in slist:
            zh = self.translate(a.summary, "en")
            if zh:
                a.summary_zh = zh
                sdone += 1
            time.sleep(self.delay)

        self.save_cache()
        logger.info(
            f"翻译完成: 标题 {done}/{len(title_pending)} 条、摘要 {sdone}/{len(summary_pending)} 条"
            f"已转为中文（缓存共 {len(self.cache)} 条）"
        )
        return done
