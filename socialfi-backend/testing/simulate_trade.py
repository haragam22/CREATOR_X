import asyncio
import logging
import json
from web3 import Web3
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.config import w3, settings, creator_abi
from app.db.session import AsyncSessionLocal
from sqlalchemy.future import select
from app.db.models import Creator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def simulate_trade(creator_id: int, action: str, amount: int = 1):
    """
    Executes a real BUY or SELL transaction on the Base Sepolia blockchain.
    """
    # 1. Fetch the creator's contract address from the DB
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Creator).where(Creator.id == creator_id))
        creator = result.scalars().first()
        
    if not creator or not creator.token_contract:
        logger.error(f"Creator {creator_id} not found or has no contract deployed.")
        return

    contract_address = w3.to_checksum_address(creator.token_contract)
    contract = w3.eth.contract(address=contract_address, abi=creator_abi)
    
    # Load ERC20 ABI for USDC interactions
    with open(os.path.join(os.path.dirname(__file__), '..', 'app', 'abis', 'erc20.json'), 'r') as f:
        erc20_abi = json.load(f)
        
    usdc_address = contract.functions.usdcAddress().call()
    usdc_contract = w3.eth.contract(address=usdc_address, abi=erc20_abi)

    # 2. Setup the test buyer wallet
    buyer_account = w3.eth.account.from_key(settings.backend_wallet_private_key)
    buyer_address = buyer_account.address
    logger.info(f"Using test wallet: {buyer_address}")
    
    # Fetch dynamic fee data
    fee_history = w3.eth.fee_history(1, 'latest', [10, 50, 90])
    base_fee = fee_history['baseFeePerGas'][-1]
    priority_fee = w3.to_wei('1', 'gwei')
    max_fee = base_fee * 2 + priority_fee

    try:
        if action.upper() == "BUY":
            logger.info(f"Fetching buy quote for {amount} pass(es)...")
            total_cost, fee = contract.functions.getBuyQuote(amount).call()
            
            # NOTE: USDC has 6 decimals! 1,000,000 micro-USDC = 1.00 USDC
            logger.info(f"Cost: {total_cost} micro-USDC (${total_cost / 1e6:.2f} USDC)")
            
            # Check Wallet USDC Balance
            usdc_balance = usdc_contract.functions.balanceOf(buyer_address).call()
            if usdc_balance < total_cost:
                logger.error(f"❌ INSUFFICIENT BALANCE: Your wallet has {usdc_balance / 1e6:.2f} USDC, but you need {total_cost / 1e6:.2f} USDC.")
                logger.error(f"👉 Please send Base Sepolia testnet USDC to your wallet: {buyer_address}")
                logger.error(f"You can mint test USDC by calling the mint function on the testnet USDC contract, or use a faucet.")
                return
                
            # Check USDC Allowance and Approve if necessary
            allowance = usdc_contract.functions.allowance(buyer_address, contract_address).call()
            if allowance < total_cost:
                logger.info(f"Approving USDC spend... (Allowance is {allowance}, needing {total_cost})")
                nonce = w3.eth.get_transaction_count(buyer_address, 'pending')
                approve_tx = usdc_contract.functions.approve(contract_address, total_cost).build_transaction({
                    'chainId': 84532,
                    'gas': 100000,
                    'maxFeePerGas': max_fee,
                    'maxPriorityFeePerGas': priority_fee,
                    'nonce': nonce,
                })
                signed_app = w3.eth.account.sign_transaction(approve_tx, private_key=settings.backend_wallet_private_key)
                
                try:
                    app_raw = signed_app.raw_transaction
                except AttributeError:
                    app_raw = signed_app.rawTransaction
                    
                app_hash = w3.eth.send_raw_transaction(app_raw)
                logger.info(f"Approval sent: {app_hash.hex()}. Waiting for confirmation...")
                w3.eth.wait_for_transaction_receipt(app_hash)
                logger.info("✅ USDC Approved!")
            else:
                logger.info("✅ USDC allowance already sufficient.")
            
            nonce = w3.eth.get_transaction_count(buyer_address, 'pending')
            tx = contract.functions.buyPass(amount).build_transaction({
                'chainId': 84532,
                'gas': 500000,
                'maxFeePerGas': max_fee,
                'maxPriorityFeePerGas': priority_fee,
                'nonce': nonce,
            })
            
        elif action.upper() == "SELL":
            logger.info(f"Fetching sell quote for {amount} pass(es)...")
            total_return, fee = contract.functions.getSellQuote(amount).call()
            logger.info(f"Return: {total_return} micro-USDC (${total_return / 1e6:.2f} USDC)")
            
            # Check if they own the pass!
            pass_balance = contract.functions.balanceOf(buyer_address, 1).call()
            if pass_balance < amount:
                logger.error(f"❌ You don't own enough passes to sell. Balance: {pass_balance}, Trying to sell: {amount}")
                return
            
            nonce = w3.eth.get_transaction_count(buyer_address, 'pending')
            tx = contract.functions.sellPass(amount).build_transaction({
                'chainId': 84532,
                'gas': 500000,
                'maxFeePerGas': max_fee,
                'maxPriorityFeePerGas': priority_fee,
                'nonce': nonce,
            })
        else:
            logger.error("Action must be BUY or SELL")
            return

        logger.info(f"Signing {action} transaction...")
        signed_tx = w3.eth.account.sign_transaction(tx, private_key=settings.backend_wallet_private_key)
        
        try:
            raw_tx = signed_tx.raw_transaction
        except AttributeError:
            raw_tx = signed_tx.rawTransaction
            
        tx_hash = w3.eth.send_raw_transaction(raw_tx)
        logger.info(f"Transaction sent! Hash: {tx_hash.hex()}")
        
        logger.info("Waiting for block confirmation (this takes a few seconds)...")
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        
        if receipt['status'] == 1:
            logger.info(f"✅ Success! {action} confirmed in block {receipt['blockNumber']}.")
            logger.info("The event_listener daemon will now detect this and update the database.")
        else:
            logger.error("❌ Transaction failed (reverted on-chain).")

    except Exception as e:
        logger.error(f"Trade failed: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python simulate_trade.py <creator_id> <BUY|SELL> [amount]")
        sys.exit(1)
        
    c_id = int(sys.argv[1])
    act = sys.argv[2]
    amt = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    
    asyncio.run(simulate_trade(c_id, act, amt))
