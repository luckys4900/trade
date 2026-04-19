from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
import logging
from btc_whale_system import MasterAgent

def setup_scheduler():
    scheduler = BlockingScheduler()
    scheduler.add_job(
        daily_cycle,
        CronTrigger(hour=0, minute=0, timezone='UTC'),
        id='btc_whale_daily',
        name='BTC Whale Daily Discovery',
        misfire_grace_time=3600
    )
    logger = logging.getLogger(__name__)
    logger.info("Scheduler configured: Daily cycle at UTC 00:00")
    return scheduler

def daily_cycle():
    agent = MasterAgent()
    result = agent.run_daily_cycle()
    return result

if __name__ == "__main__":
    scheduler = setup_scheduler()
    scheduler.start()
