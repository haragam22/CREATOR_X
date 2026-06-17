import sys, os
import asyncio
import logging

# Fix path to allow importing app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Set up simple logging
logging.basicConfig(level=logging.INFO)

# Create the event loop FIRST before importing any SQLAlchemy async engines
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

from app.tasks.candle_tasks import aggregate_5m_candles
from app.tasks.sentiment_tasks import fetch_youtube_comments, compute_modifier
from app.db.session import AsyncSessionLocal
from app.db.models import Creator
from sqlalchemy.future import select

async def main():
    print("\n--- Testing Phase 2A.6: Candle Aggregation ---")
    try:
        await aggregate_5m_candles()
        print("Candle aggregation function ran successfully!")
    except Exception as e:
        print(f"Candle aggregation failed: {e}")

    print("\n--- Testing Phase 2A.7: Sentiment Pipeline ---")
    try:
        # We will use the Google Developers channel ID: UC_x5XG1OV2P6uZZ5FSM9Ttw
        channel_id = "UC_x5XG1OV2P6uZZ5FSM9Ttw"
        print(f"Fetching comments for channel {channel_id}...")
        comments = await fetch_youtube_comments(channel_id, max_results=5)
        
        print(f"Fetched {len(comments)} comments.")
        if comments:
            print("Sample comment:", comments[0][:100], "...")
            
            print("Running NLP Sentiment pipeline...")
            modifier_bps = compute_modifier(comments)
            print(f"Computed Modifier BPS: {modifier_bps}")
        else:
            print("No comments fetched (maybe API key not set properly?)")
    except Exception as e:
        print(f"Sentiment pipeline failed: {e}")

if __name__ == "__main__":
    loop.run_until_complete(main())
