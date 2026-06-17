import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db.session import get_db
from app.db.models import Creator
from app.services.web3_service import Web3Service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/portfolio", tags=["portfolio"])

@router.get("/{wallet}")
async def get_portfolio(wallet: str, db: AsyncSession = Depends(get_db)):
    """
    Get user portfolio balances for all active creator tokens.
    """
    result = await db.execute(select(Creator).where(Creator.token_contract != None))
    creators = result.scalars().all()
    
    portfolio = []
    
    for c in creators:
        try:
            contract = Web3Service.get_creator_contract(c.token_contract)
            # Token ID is 0 for the main pass
            balance = contract.functions.balanceOf(wallet, 0).call()
            
            if balance > 0:
                current_price = contract.functions.getCurrentPrice().call()
                total_value = balance * current_price
                
                portfolio.append({
                    "creatorId": c.id,
                    "name": c.display_name,
                    "amountHeld": balance,
                    "currentPriceUsdc": current_price,
                    "totalValueUsdc": total_value,
                    "contractAddress": c.token_contract
                })
        except Exception as e:
            logger.error(f"Failed to fetch portfolio for wallet {wallet} on contract {c.token_contract}: {e}")
            
    return portfolio
