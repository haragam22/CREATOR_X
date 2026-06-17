import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import asyncio
from fastapi.testclient import TestClient
from app.main import app
from app.db.session import AsyncSessionLocal
from app.db.models import Creator
from app.core.security import create_access_token
from sqlalchemy.future import select

client = TestClient(app)

async def setup_test_user():
    async with AsyncSessionLocal() as db:
        # Check if test user exists
        result = await db.execute(select(Creator).where(Creator.google_id == "test_google_id"))
        user = result.scalars().first()
        if not user:
            user = Creator(
                google_id="test_google_id",
                display_name="Test User",
                youtube_channel_id="temp",
                wallet_address="0x1111111111111111111111111111111111111111", # using a dummy 42-char valid eth address
                tier=0,
                base_price_usdc=0,
                k_value=0
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
        
        # We need a token
        token = create_access_token({"user_id": user.id, "is_creator": False})
        return token

def test_register():
    token = asyncio.run(setup_test_user())
    print(f"Generated Test Token: {token}")

    # Call register endpoint
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "youtube_channel_id": "UC_x5XG1OV2P6uZZ5FSM9Ttw" # Google Developers
    }
    
    print("Calling POST /creators/register...")
    response = client.post("/creators/register", json=payload, headers=headers)
    
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")

if __name__ == "__main__":
    test_register()
