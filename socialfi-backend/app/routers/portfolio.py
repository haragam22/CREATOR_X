import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db.session import get_db
from app.db.models import Creator, MockPortfolio
from app.services.web3_service import Web3Service
from app.config import w3

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/portfolio", tags=["portfolio"])

@router.get("/{wallet}")
async def get_portfolio(wallet: str, db: AsyncSession = Depends(get_db)):
    """
    Get user portfolio balances for all active creator tokens.
    Merges real on-chain balances with mock off-chain balances for frontend testing.
    """
    result = await db.execute(select(Creator).where(Creator.token_contract != None))
    creators = result.scalars().all()
    
    portfolio = []
    
    for c in creators:
        balance = 0
        current_price = 0
        try:
            contract = Web3Service.get_creator_contract(c.token_contract)
            # 1. Fetch real on-chain balance
            try:
                # Wallet address must be valid hex for checksum, if dummy frontend wallet, this will fail
                checksum_wallet = w3.to_checksum_address(wallet)
                on_chain_balance = contract.functions.balanceOf(checksum_wallet, 1).call()
                balance += on_chain_balance
            except Exception as w_err:
                pass # Probably a dummy non-hex wallet from Flutter, ignore on-chain check
            
            # 2. Fetch mock balance
            mp_res = await db.execute(select(MockPortfolio).where(
                MockPortfolio.wallet_address.ilike(wallet),
                MockPortfolio.creator_id == c.id
            ))
            mp = mp_res.scalars().first()
            if mp:
                balance += mp.balance
            
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
