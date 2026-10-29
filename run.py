#!/usr/bin/env python3
"""
基督教世界新闻知识库 - 启动入口
用法:
  python run.py collect      # 立即执行一次采集
  python run.py generate     # 基于已有数据库生成站点
  python run.py full         # 采集 + 生成（默认）
  python run.py schedule     # 启动每日定时调度
"""
import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.collector import Collector
from src.generators import SiteGenerator
from src.scheduler import run_pipeline, start_scheduler
from src.utils import setup_logging

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config", "sources.yaml")
DATA_DIR = os.path.join(BASE_DIR, "data")
SITE_DIR = os.path.join(BASE_DIR, "site")
TEMPLATE_DIR = os.path.join(BASE_DIR, "src", "generators", "templates")
LOG_DIR = os.path.join(BASE_DIR, "logs")


def main():
    parser = argparse.ArgumentParser(description="基督教世界新闻知识库采集与站点生成")
    parser.add_argument("command", choices=["collect", "generate", "full", "schedule"], default="full", nargs="?")
    parser.add_argument("--workers", type=int, default=8, help="并发采集线程数")
    parser.add_argument("--hour", type=int, default=8, help="每日调度小时（默认 8 点）")
    parser.add_argument("--minute", type=int, default=30, help="每日调度分钟（默认 30 分）")
    args = parser.parse_args()

    setup_logging(log_dir=LOG_DIR)

    if args.command == "collect":
        collector = Collector(CONFIG_PATH, DATA_DIR, workers=args.workers)
        collector.collect()
        collector.save_raw()
        collector.build_database()
        collector.snapshot()
    elif args.command == "generate":
        generator = SiteGenerator(
            db_dir=os.path.join(DATA_DIR, "db"),
            site_dir=SITE_DIR,
            template_dir=TEMPLATE_DIR,
        )
        generator.generate()
    elif args.command == "schedule":
        start_scheduler(CONFIG_PATH, DATA_DIR, SITE_DIR, TEMPLATE_DIR, hour=args.hour, minute=args.minute)
    else:
        run_pipeline(CONFIG_PATH, DATA_DIR, SITE_DIR, TEMPLATE_DIR, workers=args.workers)


if __name__ == "__main__":
    main()
