import sys, os
import asyncio
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
logging.basicConfig(level=logging.ERROR)

from app.tasks.sentiment_tasks import fetch_youtube_comments
from app.services.sentiment import sentiment_pipeline

async def debug_sentiment():
    channel_id = "UC_x5XG1OV2P6uZZ5FSM9Ttw" # Google Developers
    print(f"Fetching up to 20 comments for channel: {channel_id}...\n")
    comments = await fetch_youtube_comments(channel_id, max_results=20)
    
    if not comments:
        print("No comments fetched.")
        return
        
    print(f"--- Fetched {len(comments)} Comments ---")
    
    results = sentiment_pipeline(comments, truncation=True, max_length=512)
    
    pos_count = 0
    neg_count = 0
    
    for i, (comment, result) in enumerate(zip(comments, results)):
        label = result['label']
        score = result['score']
        
        if label == 'POSITIVE':
            pos_count += 1
        else:
            neg_count += 1
            
        print(f"[{i+1}] Label: {label} (Score: {score:.4f})")
        print(f"    Comment: {comment}")
        print("-" * 50)
        
    print(f"\nFinal Tally: {pos_count} POSITIVE | {neg_count} NEGATIVE")

if __name__ == "__main__":
    asyncio.run(debug_sentiment())
