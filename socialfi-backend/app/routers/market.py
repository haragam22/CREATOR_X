import logging
from fastapi import APIRouter, HTTPException, BackgroundTasks
from app.config import factory_contract
from app.tasks.market_tasks import open_market_session, close_market_session

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/market", tags=["market"])

@router.get("/status")
async def get_market_status():
    """
    Returns whether the global market is currently open.
    """
    try:
        is_open = factory_contract.functions.isMarketOpen().call()
        return {"market_open": is_open}
    except Exception as e:
        logger.error(f"Failed to fetch market status: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch market status from blockchain.")

@router.post("/open")
async def manual_open_market(background_tasks: BackgroundTasks):
    """
    Manually triggers the market open process in the background.
    """
    background_tasks.add_task(open_market_session)
    return {"status": "processing", "action": "open_market"}

@router.post("/close")
async def manual_close_market(background_tasks: BackgroundTasks):
    """
    Manually triggers the market close process in the background.
    """
    background_tasks.add_task(close_market_session)
    return {"status": "processing", "action": "close_market"}

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends
from app.db.session import get_db
from app.db.models import Creator, MockPortfolio, PriceEvent
from app.services.web3_service import Web3Service
import time
import asyncio
from datetime import datetime, timezone
from app.websocket.manager import manager
from sqlalchemy.future import select

class MockTradeReq(BaseModel):
    wallet_address: str
    creator_id: int
    amount: int = 1

@router.post("/mock/buy")
async def mock_buy(req: MockTradeReq, db: AsyncSession = Depends(get_db)):
    """Mock a buy transaction to test the UI without Metamask"""
    try:
        res = await db.execute(select(Creator).where(Creator.id == req.creator_id))
        creator = res.scalars().first()
        if not creator or not creator.token_contract:
            raise HTTPException(status_code=404, detail="Creator or contract not found")
            
        contract = Web3Service.get_creator_contract(creator.token_contract)
        current_supply = contract.functions.currentSupply().call()
        
        # Workaround: getBuyQuote has a bug in the Solidity contract for amount > 1 
        # (returns values > 10^15). We just use the current price for the mock DB event.
        price_per_token = contract.functions.getCurrentPrice().call()
            
        new_supply = current_supply + req.amount
        tx_hash = f"mock_buy_{int(time.time() * 1000)}"
        
        # 1. Update MockPortfolio
        mp_res = await db.execute(select(MockPortfolio).where(
            MockPortfolio.wallet_address.ilike(req.wallet_address),
            MockPortfolio.creator_id == creator.id
        ))
        mp = mp_res.scalars().first()
        if mp:
            mp.balance += req.amount
        else:
            mp = MockPortfolio(wallet_address=req.wallet_address.lower(), creator_id=creator.id, balance=req.amount)
            db.add(mp)
            
        # 2. Insert fake PriceEvent
        pe = PriceEvent(
            creator_id=creator.id,
            event_type="BUY",
            price_usdc=price_per_token,
            supply=new_supply,
            tx_hash=tx_hash,
            block_number=0,
            block_timestamp=datetime.now(timezone.utc)
        )
        db.add(pe)
        await db.commit()
        
        # 3. Broadcast WebSocket tick
        tick_msg = {
            "type": "tick",
            "creator_id": creator.id,
            "data": {
                "price": price_per_token / 1e6,
                "supply": new_supply,
                "event": "buy",
                "timestamp": int(time.time())
            }
        }
        asyncio.create_task(manager.broadcast(creator.id, tick_msg))
        
        return {"status": "success", "tx_hash": tx_hash, "new_balance": mp.balance}
    except Exception as e:
        import traceback
        return {"status": "error", "message": str(e), "traceback": traceback.format_exc()}

@router.post("/mock/sell")
async def mock_sell(req: MockTradeReq, db: AsyncSession = Depends(get_db)):
    """Mock a sell transaction to test the UI without Metamask"""
    res = await db.execute(select(Creator).where(Creator.id == req.creator_id))
    creator = res.scalars().first()
    if not creator or not creator.token_contract:
        raise HTTPException(status_code=404, detail="Creator or contract not found")
        
    # Check MockPortfolio balance first
    mp_res = await db.execute(select(MockPortfolio).where(
        MockPortfolio.wallet_address.ilike(req.wallet_address),
        MockPortfolio.creator_id == creator.id
    ))
    mp = mp_res.scalars().first()
    if not mp or mp.balance < req.amount:
        raise HTTPException(status_code=400, detail=f"Insufficient mock balance. You have {mp.balance if mp else 0}.")
        
    contract = Web3Service.get_creator_contract(creator.token_contract)
    current_supply = contract.functions.currentSupply().call()
    
    # Workaround for Solidity math bug on >1 amount
    price_per_token = contract.functions.getCurrentPrice().call()
        
    new_supply = max(0, current_supply - req.amount)
    tx_hash = f"mock_sell_{int(time.time() * 1000)}"
    
    # 1. Update MockPortfolio
    mp.balance -= req.amount
        
    # 2. Insert fake PriceEvent
    pe = PriceEvent(
        creator_id=creator.id,
        event_type="SELL",
        price_usdc=price_per_token,
        supply=new_supply,
        tx_hash=tx_hash,
        block_number=0,
        block_timestamp=datetime.now(timezone.utc)
    )
    db.add(pe)
    await db.commit()
    
    # 3. Broadcast WebSocket tick
    tick_msg = {
        "type": "tick",
        "creator_id": creator.id,
        "data": {
            "price": price_per_token / 1e6,
            "supply": new_supply,
            "event": "sell",
            "timestamp": int(time.time())
        }
    }
    asyncio.create_task(manager.broadcast(creator.id, tick_msg))
    
    return {"status": "success", "tx_hash": tx_hash, "new_balance": mp.balance}
