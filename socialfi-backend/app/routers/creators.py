import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.db.session import get_db
from app.db.models import Creator
from app.routers.auth import get_current_user
from app.services.youtube import YouTubeService
from app.services.web3_service import Web3Service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/creators", tags=["creators"])

class RegisterCreatorRequest(BaseModel):
    youtube_channel_id: str

@router.post("/register")
async def register_creator(req: RegisterCreatorRequest, current_user: Creator = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if current_user.token_contract:
        raise HTTPException(status_code=400, detail="User is already registered as a creator.")
        
    if not current_user.wallet_address or current_user.wallet_address.startswith("temp_wallet_"):
        raise HTTPException(status_code=400, detail="Wallet address must be linked before registering as a creator.")

    logger.info(f"Fetching YouTube metrics for channel: {req.youtube_channel_id}")
    yt_data = await YouTubeService.get_channel_metrics(req.youtube_channel_id)
    
    tier = yt_data["tier"]
    base_price = yt_data["base_price_usdc"]
    k_value = yt_data["k_value"]
    subscribers = yt_data["subscribers"]

    logger.info(f"Deploying creator contract for {current_user.wallet_address} (Tier: {tier}, Base Price: {base_price}, K: {k_value})")
    
    try:
        # Run synchronous Web3 transaction in a threadpool to avoid blocking FastAPI event loop
        token_contract = await run_in_threadpool(
            Web3Service.deploy_creator_contract,
            creator_wallet=current_user.wallet_address,
            tier=tier,
            base_price=base_price,
            k_scaled=k_value
        )
    except Exception as e:
        logger.error(f"Failed to deploy contract: {e}")
        raise HTTPException(status_code=500, detail="Failed to deploy smart contract on-chain.")

    # Update DB with new creator profile
    current_user.youtube_channel_id = req.youtube_channel_id
    current_user.subscriber_count = subscribers
    current_user.tier = tier
    current_user.base_price_usdc = base_price
    current_user.k_value = k_value
    current_user.token_contract = token_contract

    await db.commit()
    await db.refresh(current_user)

    return {
        "status": "success",
        "token_contract": token_contract,
        "tier": tier,
        "base_price_usdc": base_price,
        "k_value": k_value,
        "subscribers": subscribers
    }

@router.get("/{creator_id}/candles")
async def get_creator_candles(creator_id: int, tf: str = "5m", db: AsyncSession = Depends(get_db)):
    """
    Get historical OHLC candles for TradingView.
    """
    if tf != "5m":
        raise HTTPException(status_code=400, detail="Only 5m timeframe supported currently")
        
    from sqlalchemy.future import select
    from app.db.models import Candle5m
    
    result = await db.execute(
        select(Candle5m)
        .where(Candle5m.creator_id == creator_id)
        .order_by(Candle5m.open_time.asc())
    )
    candles = result.scalars().all()
    
    if not candles:
        # Fetch the creator to get token contract
        from app.db.models import Creator
        from app.services.web3_service import Web3Service
        from datetime import datetime, timezone
        
        creator_result = await db.execute(select(Creator).where(Creator.id == creator_id))
        creator = creator_result.scalars().first()
        
        if creator and creator.token_contract:
            try:
                contract = Web3Service.get_creator_contract(creator.token_contract)
                current_price = contract.functions.getCurrentPrice().call()
                now = datetime.now(timezone.utc)
                return [{
                    "time": int(now.timestamp()),
                    "open": float(current_price),
                    "high": float(current_price),
                    "low": float(current_price),
                    "close": float(current_price),
                    "volume": 0
                }]
            except Exception as e:
                pass # Fallback to empty list if contract call fails
    
    return [
        {
            "time": int(c.open_time.timestamp()),
            "open": float(c.open_price),
            "high": float(c.high_price),
            "low": float(c.low_price),
            "close": float(c.close_price),
            "volume": c.volume_tokens
        }
        for c in candles
    ]

@router.get("")
async def get_all_creators(db: AsyncSession = Depends(get_db)):
    """
    Get all creators, sorted by rank score descending.
    """
    from sqlalchemy.future import select
    from app.services.sentiment import creator_rank_score
    from app.services.web3_service import Web3Service
    
    result = await db.execute(
        select(Creator).where(Creator.token_contract != None)
    )
    creators = result.scalars().all()
    
    creator_list = []
    for c in creators:
        try:
            # We fetch current price and AI modifier from the blockchain
            contract = Web3Service.get_creator_contract(c.token_contract)
            current_price = contract.functions.getCurrentPrice().call()
            ai_modifier_bps = contract.functions.aiModifierBps().call()
            
            # Note: In a production app with high load, we'd cache engagement_score and rank score 
            # in the database instead of computing them and hitting RPC per creator per request.
            # But this matches the Phase 2A.9 specs exactly.
            
            c_dict = {
                "id": c.id,
                "name": c.display_name,
                "tier": c.tier,
                "price": current_price,
                "aiModifierBps": ai_modifier_bps,
                "contractAddress": c.token_contract,
            }
            
            # Compute rank score for sorting
            creator_data_for_ranking = {
                "ai_modifier_bps": ai_modifier_bps,
                "engagement_score": 0.5, # Placeholder engagement since we don't have historical metrics saved yet
                "days_since_last_upload": 7, # Placeholder
                "subscriber_count": c.subscriber_count or 0
            }
            c_dict["_rank_score"] = creator_rank_score(creator_data_for_ranking)
            
            creator_list.append(c_dict)
            
        except Exception as e:
            logger.error(f"Error fetching data for creator {c.id}: {e}")
            
    # Sort descending
    creator_list.sort(key=lambda x: x["_rank_score"], reverse=True)
    
    # Strip rank score from output payload
    for c in creator_list:
        del c["_rank_score"]
        
    return creator_list

@router.get("/{creator_id}")
async def get_creator_detail(creator_id: int, db: AsyncSession = Depends(get_db)):
    """
    Get full details for a creator.
    """
    from sqlalchemy.future import select
    from app.services.web3_service import Web3Service
    
    result = await db.execute(select(Creator).where(Creator.id == creator_id))
    creator = result.scalars().first()
    
    if not creator:
        raise HTTPException(status_code=404, detail="Creator not found")
        
    contract_data = {}
    if creator.token_contract:
        try:
            contract = Web3Service.get_creator_contract(creator.token_contract)
            current_price = contract.functions.getCurrentPrice().call()
            ai_modifier_bps = contract.functions.aiModifierBps().call()
            current_supply = contract.functions.currentSupply().call()
            session_opening_price = contract.functions.sessionOpeningPrice().call()
            
            contract_data = {
                "price": current_price,
                "aiModifierBps": ai_modifier_bps,
                "currentSupply": current_supply,
                "sessionOpeningPrice": session_opening_price
            }
        except Exception as e:
            logger.error(f"Error fetching contract data for {creator.id}: {e}")
            
    return {
        "id": creator.id,
        "name": creator.display_name,
        "wallet": creator.wallet_address,
        "youtubeId": creator.youtube_channel_id,
        "subscribers": creator.subscriber_count,
        "tier": creator.tier,
        "contractAddress": creator.token_contract,
        "onChainData": contract_data
    }

@router.get("/{creator_id}/quote/buy")
async def get_buy_quote(creator_id: int, amount: int = 1, db: AsyncSession = Depends(get_db)):
    from sqlalchemy.future import select
    from app.services.web3_service import Web3Service
    
    result = await db.execute(select(Creator).where(Creator.id == creator_id))
    creator = result.scalars().first()
    if not creator or not creator.token_contract:
        raise HTTPException(status_code=404, detail="Creator contract not found")
        
    return Web3Service.get_buy_quote(creator.token_contract, amount)

@router.get("/{creator_id}/quote/sell")
async def get_sell_quote(creator_id: int, amount: int = 1, db: AsyncSession = Depends(get_db)):
    from sqlalchemy.future import select
    from app.services.web3_service import Web3Service
    
    result = await db.execute(select(Creator).where(Creator.id == creator_id))
    creator = result.scalars().first()
    if not creator or not creator.token_contract:
        raise HTTPException(status_code=404, detail="Creator contract not found")
        
    return Web3Service.get_sell_quote(creator.token_contract, amount)

@router.get("/{creator_id}/sentiment")
async def get_sentiment(creator_id: int, db: AsyncSession = Depends(get_db)):
    from sqlalchemy.future import select
    from app.db.models import SentimentHistory
    
    result = await db.execute(
        select(SentimentHistory)
        .where(SentimentHistory.creator_id == creator_id)
        .order_by(SentimentHistory.computed_at.desc())
        .limit(1)
    )
    history = result.scalars().first()
    if not history:
        return {"modifier_bps": 10000, "raw_score": 1.0, "comment_sample": 0}
        
    return {
        "modifier_bps": history.modifier_bps,
        "raw_score": history.raw_score,
        "comment_sample": history.comment_sample,
        "computed_at": history.computed_at
    }
