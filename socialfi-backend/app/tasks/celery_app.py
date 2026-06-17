from celery import Celery
from celery.schedules import crontab
from app.config import settings
import asyncio
import nest_asyncio

# Apply nest_asyncio to allow asyncio.run inside celery workers if needed
nest_asyncio.apply()

celery_app = Celery(
    "socialfi_tasks",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks.market_tasks", "app.tasks.candle_tasks", "app.tasks.sentiment_tasks"]
)

celery_app.conf.beat_schedule = {
    'open-morning':  {
        'task': 'app.tasks.market_tasks.run_open_market',
        'schedule': crontab(hour=4, minute=30) # 10:00 IST = 04:30 UTC
    },
    'close-morning': {
        'task': 'app.tasks.market_tasks.run_close_market',
        'schedule': crontab(hour=8, minute=30) # 14:00 IST = 08:30 UTC
    },
    'open-evening':  {
        'task': 'app.tasks.market_tasks.run_open_market',
        'schedule': crontab(hour=12, minute=30) # 18:00 IST = 12:30 UTC
    },
    'close-evening': {
        'task': 'app.tasks.market_tasks.run_close_market',
        'schedule': crontab(hour=16, minute=30) # 22:00 IST = 16:30 UTC
    },
    'candles': {
        'task': 'app.tasks.candle_tasks.run_aggregate_candles',
        'schedule': crontab(minute='*/5')
    },
    'sentiment': {
        'task': 'app.tasks.sentiment_tasks.run_sentiment_pipeline_task',
        'schedule': crontab(minute='*/30')
    },
}

celery_app.conf.timezone = 'UTC'

# Sync wrappers for the async functions to be called by Celery

@celery_app.task
def run_open_market():
    from app.tasks.market_tasks import open_market_session
    asyncio.run(open_market_session())

@celery_app.task
def run_close_market():
    from app.tasks.market_tasks import close_market_session
    asyncio.run(close_market_session())

@celery_app.task
def run_aggregate_candles():
    from app.tasks.candle_tasks import aggregate_5m_candles
    asyncio.run(aggregate_5m_candles())

@celery_app.task
def run_sentiment_pipeline_task():
    from app.tasks.sentiment_tasks import run_all_creators
    asyncio.run(run_all_creators())
