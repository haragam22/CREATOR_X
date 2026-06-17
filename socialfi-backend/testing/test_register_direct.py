import sys, os
import asyncio

# Fix path to allow importing app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Create the event loop FIRST before importing any SQLAlchemy async engines
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

from app.db.session import AsyncSessionLocal
from app.db.models import Creator
from app.routers.creators import register_creator, RegisterCreatorRequest
from sqlalchemy.future import select

async def main():
    print("Setting up test user in DB...")
    async with AsyncSessionLocal() as db:
        # Create or fetch test user
        result = await db.execute(select(Creator).where(Creator.google_id == "test_direct_id"))
        user = result.scalars().first()
        if not user:
            user = Creator(
                google_id="test_direct_id",
                display_name="Direct Test User",
                youtube_channel_id="temp_direct",
                wallet_address="0x2222222222222222222222222222222222222222",
                tier=0,
                base_price_usdc=0,
                k_value=0
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)

        print(f"Test User ID: {user.id}")
        
        # We need to simulate the FastAPI request
        req = RegisterCreatorRequest(youtube_channel_id="UC_x5XG1OV2P6uZZ5FSM9Ttw")
        
        try:
            print("Invoking register_creator directly...")
            res = await register_creator(req=req, current_user=user, db=db)
            print("SUCCESS! Response from register_creator:")
            print(res)
        except Exception as e:
            print(f"FAILED: {e}")

if __name__ == "__main__":
    loop.run_until_complete(main())
