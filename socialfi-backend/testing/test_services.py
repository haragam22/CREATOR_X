import asyncio
import os
import requests
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from web3 import Web3
import redis.asyncio as redis
from dotenv import load_dotenv

load_dotenv()

async def test_all():
    print("\n" + "="*50)
    print("RUNNING COMPREHENSIVE BACKEND SERVICES TEST")
    print("="*50 + "\n")
    
    # 1. Test Supabase Database
    print("[1/5] Testing PostgreSQL Database (Supabase)...")
    db_url = os.getenv("DATABASE_URL")
    try:
        engine = create_async_engine(db_url)
        async with engine.connect() as conn:
            res = await conn.execute(text("SELECT version();"))
            version = res.scalar()
            print(f"  [SUCCESS] Connected to Supabase DB!")
            print(f"  [INFO] Version: {version[:40]}...")
    except Exception as e:
        print(f"  [FAILED] Database connection error:\n{e}")

    # 2. Test Redis
    print("\n[2/5] Testing Redis Server (Upstash)...")
    redis_url = os.getenv("REDIS_URL")
    try:
        r = redis.from_url(redis_url)
        ping = await r.ping()
        if ping:
            print("  [SUCCESS] Redis Ping successful!")
        else:
            print("  [FAILED] Redis Ping failed.")
        await r.aclose()
    except Exception as e:
        print(f"  [FAILED] Redis connection error:\n{e}")

    # 3. Test Web3 / Base Sepolia
    print("\n[3/5] Testing Blockchain (Base Sepolia)...")
    rpc_url = os.getenv("BASE_SEPOLIA_RPC")
    try:
        w3 = Web3(Web3.HTTPProvider(rpc_url))
        if w3.is_connected():
            print(f"  [SUCCESS] Connected to Base Sepolia!")
            print(f"  [INFO] Current Block: {w3.eth.block_number}")
        else:
            print("  [FAILED] Could not connect to Web3 RPC.")
    except Exception as e:
        print(f"  [FAILED] Web3 error:\n{e}")

    # 4. Test YouTube API
    print("\n[4/5] Testing YouTube API...")
    yt_api_key = os.getenv("YOUTUBE_API_KEY")
    # Google Developers channel ID for testing
    test_channel_id = "UC_x5XG1OV2P6uZZ5FSM9Ttw" 
    try:
        url = f"https://www.googleapis.com/youtube/v3/channels?part=statistics&id={test_channel_id}&key={yt_api_key}"
        resp = requests.get(url)
        if resp.status_code == 200:
            data = resp.json()
            if "items" in data and len(data["items"]) > 0:
                stats = data["items"][0]["statistics"]
                print(f"  [SUCCESS] YouTube API Key is valid!")
                print(f"  [INFO] Test Channel Subscribers: {stats.get('subscriberCount')}")
            else:
                print("  [FAILED] Channel not found.")
        else:
            print(f"  [FAILED] YouTube API returned {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"  [FAILED] YouTube request error:\n{e}")

    # 5. Test Google OAuth Setup
    print("\n[5/5] Testing Google OAuth Configuration...")
    google_client_id = os.getenv("GOOGLE_CLIENT_ID")
    if google_client_id and "googleusercontent.com" in google_client_id:
        print(f"  [SUCCESS] Google Client ID is configured correctly.")
        print(f"  [INFO] Client ID: {google_client_id[:15]}...{google_client_id[-10:]}")
    else:
        print("  [FAILED] Google Client ID appears to be missing or invalid.")
        
    print("\n" + "="*50)

if __name__ == "__main__":
    asyncio.run(test_all())
