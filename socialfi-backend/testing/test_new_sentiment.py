import sys, os
import asyncio
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
logging.basicConfig(level=logging.ERROR)

from app.tasks.sentiment_tasks import fetch_youtube_comments
from app.services.sentiment import compute_modifier, sentiment_pipeline

async def debug_sentiment():
    if not sentiment_pipeline:
        print("Pipeline failed to load.")
        return

    channel_id = "UC_x5XG1OV2P6uZZ5FSM9Ttw" # Google Developers
    print(f"Fetching up to 20 comments for channel: {channel_id}...\n")
    comments = await fetch_youtube_comments(channel_id, max_results=20)
    
    if not comments:
        print("No comments fetched.")
        return
        
    print(f"--- Fetched {len(comments)} Comments ---")
    
    bps = compute_modifier(comments)
    print(f"\nFinal Calculated BPS: {bps}")

if __name__ == "__main__":
    asyncio.run(debug_sentiment())
