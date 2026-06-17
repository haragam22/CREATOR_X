import asyncio
from app.db.session import AsyncSessionLocal
from app.db.models import Creator
from sqlalchemy import text

async def test_db():
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("SELECT name FROM sqlite_master WHERE type='table';"))
        tables = [row[0] for row in result]
        print(f"Connected to DB successfully. Tables present: {tables}")

if __name__ == "__main__":
    asyncio.run(test_db())
