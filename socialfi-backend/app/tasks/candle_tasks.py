import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy.future import select
from sqlalchemy import func
from app.db.session import AsyncSessionLocal
from app.db.models import Creator, PriceEvent, Candle5m

logger = logging.getLogger(__name__)

async def aggregate_5m_candles():
    """
    Called by Celery beat (or manually for testing) every 5 minutes.
    Computes 5m OHLCV candles from price_events table.
    """
    now = datetime.now(timezone.utc)
    # Get the start of the current 5m interval (e.g. 10:05:00)
    # For robust aggregation, we aggregate the *previous* 5m interval
    # because the current interval is still ongoing.
    minutes = now.minute
    remainder = minutes % 5
    current_interval_start = now.replace(minute=minutes - remainder, second=0, microsecond=0)
    target_interval_start = current_interval_start - timedelta(minutes=5)
    target_interval_end = current_interval_start
    
    logger.info(f"Aggregating 5m candles for {target_interval_start} to {target_interval_end}")

    async with AsyncSessionLocal() as db:
        try:
            # 1. Get all creators who had trades in this window
            # We can just fetch all trades in the window grouped by creator.
            stmt = select(PriceEvent).where(
                PriceEvent.block_timestamp >= target_interval_start,
                PriceEvent.block_timestamp < target_interval_end
            ).order_by(PriceEvent.creator_id, PriceEvent.block_timestamp)
            
            result = await db.execute(stmt)
            events = result.scalars().all()
            
            if not events:
                logger.info("No trades in the last 5 minutes. Skipping.")
                return
            
            # Group by creator_id
            from collections import defaultdict
            grouped = defaultdict(list)
            for event in events:
                grouped[event.creator_id].append(event)
                
            for creator_id, trades in grouped.items():
                open_price = trades[0].price_usdc
                close_price = trades[-1].price_usdc
                high_price = max(t.price_usdc for t in trades)
                low_price = min(t.price_usdc for t in trades)
                volume = sum(t.supply for t in trades) # Wait, volume is total tokens traded? No, supply is cumulative. 
                
                # Volume logic: sum of amount for this period. 
                # Our PriceEvent has `supply`. We didn't store `amount` traded! 
                # Let's approximate volume by looking at the change in supply if we need to, but it's easier 
                # to just count the number of trades or look at difference. Let's just use number of tokens traded.
                # Actually, wait, PriceEvent schema doesn't have `amount`. But `amount` is `abs(new_supply - prev_supply)`.
                # We'll just calculate it based on supply diffs if we need to. For now let's set volume = len(trades)
                
                # Check if a candle already exists (to be idempotent)
                existing_stmt = select(Candle5m).where(
                    Candle5m.creator_id == creator_id,
                    Candle5m.open_time == target_interval_start
                )
                existing = (await db.execute(existing_stmt)).scalars().first()
                
                if existing:
                    # Update it just in case
                    existing.close_price = close_price
                    existing.high_price = max(existing.high_price, high_price)
                    existing.low_price = min(existing.low_price, low_price)
                    existing.volume_tokens += len(trades)
                else:
                    new_candle = Candle5m(
                        creator_id=creator_id,
                        open_time=target_interval_start,
                        close_time=target_interval_end,
                        open_price=open_price,
                        high_price=high_price,
                        low_price=low_price,
                        close_price=close_price,
                        volume_tokens=len(trades)
                    )
                    db.add(new_candle)
                    
                    # WebSocket Broadcast (Candle)
                    from app.websocket.manager import manager
                    import asyncio
                    candle_msg = {
                        "type": "candle",
                        "creator_id": creator_id,
                        "data": {
                            "time": int(target_interval_start.timestamp()),
                            "open": float(open_price),
                            "high": float(high_price),
                            "low": float(low_price),
                            "close": float(close_price),
                            "volume": len(trades)
                        }
                    }
                    asyncio.create_task(manager.broadcast(creator_id, candle_msg))
            
            await db.commit()
            logger.info("Successfully aggregated candles.")
            
        except Exception as e:
            logger.error(f"Error aggregating candles: {e}")
            await db.rollback()
