import httpx
from fastapi import HTTPException
from app.config import settings

class YouTubeService:
    BASE_URL = "https://www.googleapis.com/youtube/v3/channels"

    @staticmethod
    async def get_channel_metrics(channel_id: str) -> dict:
        """
        Fetches subscriber count and determines Tier, Base Price, and K Value.
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                YouTubeService.BASE_URL,
                params={
                    "part": "statistics,snippet",
                    "id": channel_id,
                    "key": settings.youtube_api_key
                }
            )

        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to fetch YouTube metrics")
        
        data = response.json()
        if not data.get("items"):
            raise HTTPException(status_code=404, detail="YouTube channel not found")

        stats = data["items"][0].get("statistics", {})
        snippet = data["items"][0].get("snippet", {})
        
        subscribers = int(stats.get("subscriberCount", 0))
        channel_name = snippet.get("title", "")

        tier, base_price, k_value = YouTubeService.compute_tier(subscribers)

        return {
            "channel_id": channel_id,
            "channel_name": channel_name,
            "subscribers": subscribers,
            "tier": tier,
            "base_price_usdc": base_price,
            "k_value": k_value
        }

    @staticmethod
    def compute_tier(subscribers: int):
        # Tier 0 (Micro): < 100k subs -> base_price = 1 USDC, k_value = 1
        # Tier 1 (Mid): 100k to < 1M -> base_price = 5 USDC, k_value = 5
        # Tier 2 (Star): >= 1M -> base_price = 10 USDC, k_value = 10
        
        if subscribers < 100_000:
            return 0, 1, 1
        elif subscribers < 1_000_000:
            return 1, 5, 5
        else:
            return 2, 10, 10
