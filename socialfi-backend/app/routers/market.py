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
