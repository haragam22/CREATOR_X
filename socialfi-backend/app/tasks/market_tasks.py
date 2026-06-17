import logging
from app.config import w3, factory_contract, settings
from sqlalchemy.future import select
from app.db.session import AsyncSessionLocal
from app.db.models import Creator
from app.services.web3_service import Web3Service

logger = logging.getLogger(__name__)

async def open_market_session():
    """
    Opens the global market and all individual creator sessions.
    """
    logger.info("Opening market session...")
    try:
        # 1. Set global market open
        tx = factory_contract.functions.setMarketOpen(True).build_transaction({
            'from': settings.protocol_treasury_address, # Wait, factory owner is Oracle. 
            'nonce': w3.eth.get_transaction_count(w3.eth.account.from_key(settings.backend_wallet_private_key).address),
            'gas': 1000000,
            'gasPrice': w3.eth.gas_price
        })
        signed_tx = w3.eth.account.sign_transaction(tx, private_key=settings.backend_wallet_private_key)
        try:
            raw_tx = signed_tx.raw_transaction
        except AttributeError:
            raw_tx = signed_tx.rawTransaction
        tx_hash = w3.eth.send_raw_transaction(raw_tx)
        w3.eth.wait_for_transaction_receipt(tx_hash)
        logger.info("Global market opened successfully on factory.")
        
        # Broadcast Market Status
        from app.websocket.manager import manager
        import asyncio
        import time
        asyncio.create_task(manager.broadcast_all({
            "type": "market_status",
            "data": {
                "isOpen": True,
                "sessionEnd": int(time.time()) + 14400 # 4 hours roughly
            }
        }))
        
        # 2. Open individual sessions
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Creator).where(Creator.token_contract != None))
            creators = result.scalars().all()
            
        for creator in creators:
            contract = Web3Service.get_creator_contract(creator.token_contract)
            try:
                # openSession is permissionless!
                tx = contract.functions.openSession().build_transaction({
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
                w3.eth.send_raw_transaction(raw_tx)
                logger.info(f"Opened session for creator {creator.id}")
            except Exception as e:
                logger.error(f"Failed to open session for creator {creator.id}: {e}")
                
    except Exception as e:
        logger.error(f"Failed to open market: {e}")


async def close_market_session():
    """
    Closes the global market and all individual creator sessions.
    """
    logger.info("Closing market session...")
    try:
        # 1. Set global market closed
        tx = factory_contract.functions.setMarketOpen(False).build_transaction({
            'from': w3.eth.account.from_key(settings.backend_wallet_private_key).address,
            'nonce': w3.eth.get_transaction_count(w3.eth.account.from_key(settings.backend_wallet_private_key).address),
            'gas': 1000000,
            'gasPrice': w3.eth.gas_price
        })
        signed_tx = w3.eth.account.sign_transaction(tx, private_key=settings.backend_wallet_private_key)
        try:
            raw_tx = signed_tx.raw_transaction
        except AttributeError:
            raw_tx = signed_tx.rawTransaction
        tx_hash = w3.eth.send_raw_transaction(raw_tx)
        w3.eth.wait_for_transaction_receipt(tx_hash)
        logger.info("Global market closed successfully on factory.")
        
        # Broadcast Market Status
        from app.websocket.manager import manager
        import asyncio
        import time
        asyncio.create_task(manager.broadcast_all({
            "type": "market_status",
            "data": {
                "isOpen": False,
                "nextOpen": int(time.time()) + 28800 # 8 hours roughly
            }
        }))
        
        # 2. Close individual sessions
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Creator).where(Creator.token_contract != None))
            creators = result.scalars().all()
            
        for creator in creators:
            contract = Web3Service.get_creator_contract(creator.token_contract)
            try:
                # closeSession requires Oracle
                tx = contract.functions.closeSession().build_transaction({
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
                w3.eth.send_raw_transaction(raw_tx)
                logger.info(f"Closed session for creator {creator.id}")
            except Exception as e:
                logger.error(f"Failed to close session for creator {creator.id}: {e}")
                
    except Exception as e:
        logger.error(f"Failed to close market: {e}")
