import logging
import httpx
from sqlalchemy.future import select
from app.db.session import AsyncSessionLocal
from app.db.models import Creator, SentimentHistory
from app.services.sentiment import compute_modifier
from app.services.oracle import OracleService
from app.config import settings

logger = logging.getLogger(__name__)

async def fetch_youtube_comments(channel_id: str, max_results: int = 100) -> list[str]:
    """
    Fetch the latest comments from the channel's videos.
    For simplicity, we fetch comment threads for the channel.
    """
    logger.info(f"Fetching comments for channel: {channel_id}")
    url = f"https://www.googleapis.com/youtube/v3/commentThreads"
    params = {
        "part": "snippet",
        "allThreadsRelatedToChannelId": channel_id,
        "maxResults": max_results,
        "key": settings.youtube_api_key
    }
    
    comments = []
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            
            for item in data.get("items", []):
                snippet = item["snippet"]["topLevelComment"]["snippet"]
                text = snippet.get("textOriginal", "")
                if text:
                    comments.append(text)
    except Exception as e:
        logger.error(f"Failed to fetch comments for {channel_id}: {e}")
        
    return comments

async def run_nlp_pipeline(creator: Creator, comments: list[str]):
    """
    Runs NLP pipeline and updates database/on-chain if needed.
    """
    if not comments:
        logger.info(f"No comments found for creator {creator.id}")
        return
        
    modifier_bps = compute_modifier(comments)
    
    # Check if we should update on-chain (only if change >= 5%)
    # Since initial BPS is 10000, 5% is 500 bps
    # But wait, how do we know current bps? From the DB history.
    async with AsyncSessionLocal() as db:
        stmt = select(SentimentHistory).where(SentimentHistory.creator_id == creator.id).order_by(SentimentHistory.computed_at.desc()).limit(1)
        result = await db.execute(stmt)
        last_history = result.scalars().first()
        
        current_bps = last_history.modifier_bps if last_history else 10000
        
        tx_hash = None
        if abs(modifier_bps - current_bps) / current_bps >= 0.05:
            logger.info(f"Creator {creator.id}: Sentiment changed significantly ({current_bps} -> {modifier_bps}). Updating on-chain.")
            try:
                # Need to use threadpool because OracleService is sync Web3
                import asyncio
                loop = asyncio.get_event_loop()
                tx_hash = await loop.run_in_executor(None, OracleService.update_sentiment, creator.token_contract, modifier_bps)
            except Exception as e:
                logger.error(f"Failed to update on-chain sentiment: {e}")
        else:
            logger.info(f"Creator {creator.id}: Sentiment change too small ({current_bps} -> {modifier_bps}). Skipping on-chain update.")
            
        # Save history
        history = SentimentHistory(
            creator_id=creator.id,
            modifier_bps=modifier_bps,
            raw_score=(modifier_bps / 10000.0),
            comment_sample=len(comments),
            tx_hash=tx_hash
        )
        db.add(history)
        await db.commit()

async def run_all_creators():
    """
    Runs sentiment analysis for all active creators.
    Called by Celery beat.
    """
    logger.info("Starting run_all_creators sentiment task...")
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Creator).where(Creator.token_contract != None))
        creators = result.scalars().all()
        
    for creator in creators:
        comments = await fetch_youtube_comments(creator.youtube_channel_id)
        await run_nlp_pipeline(creator, comments)
        
    logger.info("Completed run_all_creators sentiment task.")
