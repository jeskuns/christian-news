"""
每日自动更新调度器（基于 APScheduler）
香港时区每日 08:30 执行采集、站点生成与发布
"""
import os
import time
import logging
from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler

from .collector import Collector
from .generators import SiteGenerator
from .utils import setup_logging, HK_TZ, ensure_dir

logger = logging.getLogger(__name__)


def run_pipeline(config_path: str, data_dir: str, site_dir: str, template_dir: str, workers: int = 8):
    """执行一次完整采集+生成流程"""
    logger.info("=" * 50)
    logger.info("Daily pipeline started")
    start = datetime.now(HK_TZ)

    collector = Collector(config_path, data_dir, workers=workers)
    collector.collect()
    collector.save_raw()
    collector.build_database()
    snap = collector.snapshot()

    generator = SiteGenerator(
        db_dir=os.path.join(data_dir, "db"),
        site_dir=site_dir,
        template_dir=template_dir,
    )
    generator.generate()

    elapsed = (datetime.now(HK_TZ) - start).total_seconds()
    logger.info(f"Daily pipeline finished in {elapsed:.1f}s, total articles: {snap.total}, errors: {len(snap.errors)}")
    logger.info("=" * 50)
    return snap


def start_scheduler(config_path: str, data_dir: str, site_dir: str, template_dir: str, hour: int = 8, minute: int = 30):
    """启动每日定时调度"""
    setup_logging()
    scheduler = BlockingScheduler(timezone=HK_TZ)
    scheduler.add_job(
        run_pipeline,
        "cron",
        hour=hour,
        minute=minute,
        args=(config_path, data_dir, site_dir, template_dir),
        id="daily_christian_news_update",
        replace_existing=True,
    )
    logger.info(f"Scheduler started, will run daily at {hour:02d}:{minute:02d} (Asia/Hong_Kong)")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped")
