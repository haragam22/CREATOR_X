import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db.session import get_db
from app.db.models import Creator, PriceEvent
from app.routers.auth import get_current_user
from app.services.web3_service import Web3Service
from app.config import w3, settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dashboard", tags=["dashboard"])

@router.get("/earnings")
async def get_earnings(current_user: Creator = Depends(get_current_user)):
    """
    Get creator's accrued fee balance from their smart contract.
    """
    if not current_user.token_contract:
        return {"earnings_usdc": 0}
        
    try:
        contract = Web3Service.get_creator_contract(current_user.token_contract)
        balance = contract.functions.creatorFeeBalance().call()
        return {"earnings_usdc": balance}
    except Exception as e:
        logger.error(f"Failed to fetch earnings for {current_user.id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch earnings from blockchain.")

@router.post("/withdraw")
async def withdraw_earnings(current_user: Creator = Depends(get_current_user)):
    """
    Withdraw accrued creator fees.
    In a real app, the creator would sign this tx via WalletConnect.
    For this demo backend, we proxy it via the Oracle wallet to avoid needing frontend wallet connections.
    """
    if not current_user.token_contract:
        raise HTTPException(status_code=400, detail="No creator contract found.")
        
    try:
        contract = Web3Service.get_creator_contract(current_user.token_contract)
        
        tx = contract.functions.creatorWithdraw().build_transaction({
            'from': w3.eth.account.from_key(settings.backend_wallet_private_key).address,
            'nonce': w3.eth.get_transaction_count(w3.eth.account.from_key(settings.backend_wallet_private_key).address),
            'gas': 500000,
            'gasPrice': w3.eth.gas_price
        })
        signed_tx = w3.eth.account.sign_transaction(tx, private_key=settings.backend_wallet_private_key)
        
        try:
            raw_tx = signed_tx.raw_transaction
        except AttributeError:
            raw_tx = signed_tx.rawTransaction
            
        tx_hash = w3.eth.send_raw_transaction(raw_tx)
        w3.eth.wait_for_transaction_receipt(tx_hash)
        
        return {"status": "success", "tx_hash": tx_hash.hex()}
    except Exception as e:
        logger.error(f"Failed to withdraw earnings: {e}")
        raise HTTPException(status_code=500, detail="Failed to process withdrawal.")

@router.get("/transactions")
async def get_transactions(current_user: Creator = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """
    Get recent transaction events for this creator's token.
    """
    if not current_user.token_contract:
        return []
        
    result = await db.execute(
        select(PriceEvent)
        .where(PriceEvent.creator_id == current_user.id)
        .order_by(PriceEvent.block_timestamp.desc())
        .limit(50)
    )
    events = result.scalars().all()
    
    return [
        {
            "id": e.id,
            "event_type": e.event_type,
            "tx_hash": e.tx_hash,
            "price_usdc": float(e.price_usdc),
            "supply": e.supply,
            "block_number": e.block_number,
            "timestamp": int(e.block_timestamp.timestamp())
        }
        for e in events
    ]
