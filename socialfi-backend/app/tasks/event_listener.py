import asyncio
import logging
from app.config import w3, factory_contract
from app.db.session import AsyncSessionLocal
from app.db.models import PriceEvent
from sqlalchemy.ext.asyncio import AsyncSession
import json

logger = logging.getLogger(__name__)

async def process_logs(from_block: int, to_block: int, db: AsyncSession):
    try:
        # 1. Fetch CreatorDeployed from Factory
        creator_deployed_logs = factory_contract.events.CreatorDeployed().get_logs(from_block=from_block, to_block=to_block)
        for log in creator_deployed_logs:
            creator_id = log['args']['creatorId']
            token_contract = log['args']['tokenContract']
            logger.info(f"New Creator Deployed! ID: {creator_id}, Contract: {token_contract}")
            
        # 2. Fetch PassBought and PassSold globally
        bought_sig = w3.keccak(text="PassBought(address,uint256,uint256,uint256,uint256,uint256)").hex()
        sold_sig = w3.keccak(text="PassSold(address,uint256,uint256,uint256,uint256,uint256)").hex()
        
        logs = w3.eth.get_logs({
            'fromBlock': from_block,
            'toBlock': to_block,
            'topics': [[bought_sig, sold_sig]]
        })

        for log in logs:
            token_contract = log['address']
            tx_hash = log['transactionHash'].hex()
            block_num = log['blockNumber']
            topic0 = log['topics'][0].hex()
            
            event_type = "BUY" if topic0 == bought_sig else "SELL"
            
            # Look up creator by token contract
            from sqlalchemy.future import select
            from app.db.models import Creator
            result = await db.execute(select(Creator).where(Creator.token_contract.ilike(token_contract)))
            creator = result.scalars().first()
            if not creator:
                continue # Unknown token
                
            data = log['data'].hex()
            if data.startswith('0x'):
                data = data[2:]
            
            # data contains 5 uint256: amount, pricePerToken, totalCost/Return, newSupply, timestamp
            amount = int(data[0:64], 16)
            price_per_token = int(data[64:128], 16)
            total_cost_return = int(data[128:192], 16)
            new_supply = int(data[192:256], 16)
            timestamp = int(data[256:320], 16)
            
            from datetime import datetime, timezone
            dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)

            # Insert into database
            pe = PriceEvent(
                creator_id=creator.id,
                event_type=event_type,
                price_usdc=price_per_token,
                supply=new_supply,
                tx_hash=tx_hash,
                block_number=block_num,
                block_timestamp=dt
            )
            db.add(pe)
            
            # WebSocket Broadcast (Tick)
            from app.websocket.manager import manager
            tick_msg = {
                "type": "tick",
                "creator_id": creator.id,
                "data": {
                    "price": price_per_token / 1e6, # Scale down USDC for frontend
                    "supply": new_supply,
                    "event": event_type.lower(),
                    "timestamp": timestamp
                }
            }
            # Broadcast asynchronously
            asyncio.create_task(manager.broadcast(creator.id, tick_msg))
        
        await db.commit()

    except Exception as e:
        logger.error(f"Error processing logs: {e}")
        await db.rollback()

async def event_listener_daemon():
    """
    Loops forever, polling for new blocks and fetching events.
    """
    logger.info("Starting Web3 Event Listener Daemon...")
    last_block = w3.eth.block_number

    while True:
        try:
            current_block = w3.eth.block_number
            if current_block > last_block:
                async with AsyncSessionLocal() as db:
                    await process_logs(last_block + 1, current_block, db)
                last_block = current_block
        except Exception as e:
            logger.error(f"Event Listener encountered error: {e}")
        
        await asyncio.sleep(5)  # Poll every 5 seconds
