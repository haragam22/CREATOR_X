import logging
from web3 import Web3
from fastapi import HTTPException
from app.config import w3, factory_contract, oracle_account, settings

logger = logging.getLogger(__name__)

class Web3Service:
    @staticmethod
    def deploy_creator_contract(creator_wallet: str, tier: int, base_price: int, k_scaled: int) -> str:
        """
        Deploys a CreatorToken smart contract on Base Sepolia.
        Base Price is scaled to 6 decimals (USDC).
        K Value is scaled to 18 decimals (WAD).
        """
        try:
            checksum_wallet = Web3.to_checksum_address(creator_wallet)
            
            # 1. DEVELOPMENT BYPASS: Prevent 0 values from reverting the smart contract
            # If database values are 0, apply valid test parameters (e.g., 1 USDC base price, 1 K scaling factor)
            test_base_price = base_price if base_price > 0 else 1 
            test_k_scaled = k_scaled if k_scaled > 0 else 1
            
            base_price_scaled = test_base_price * (10 ** 6)
            k_scaled_wad = test_k_scaled * (10 ** 18)
            
            # 2. FIX ADDRESS DISCREPANCY: Derive the signer address directly from your backend private key
            signer_account = w3.eth.account.from_key(settings.backend_wallet_private_key)
            nonce = w3.eth.get_transaction_count(signer_account.address, 'pending')
            
            # Fetch dynamic fee data for Base Sepolia
            fee_history = w3.eth.fee_history(1, 'latest', [10, 50, 90])
            base_fee = fee_history['baseFeePerGas'][-1]
            priority_fee = w3.to_wei('1', 'gwei')
            max_fee = base_fee * 2 + priority_fee

            # Build the transaction
            tx = factory_contract.functions.deployCreator(
                checksum_wallet,
                tier,
                base_price_scaled,
                k_scaled_wad
            ).build_transaction({
                'chainId': 84532,
                'gas': 3000000,
                'maxFeePerGas': max_fee,
                'maxPriorityFeePerGas': priority_fee,
                'nonce': nonce,
            })

            logger.info(f"Deploying creator contract from deployer address: {signer_account.address} for user: {checksum_wallet}...")
            
            # Sign and send transaction
            signed_tx = w3.eth.account.sign_transaction(tx, private_key=settings.backend_wallet_private_key)
            try:
                raw_tx = signed_tx.raw_transaction
            except AttributeError:
                raw_tx = signed_tx.rawTransaction
                
            tx_hash = w3.eth.send_raw_transaction(raw_tx)
            
            logger.info(f"Transaction sent! Hash: {tx_hash.hex()}. Waiting for receipt...")
            
            # Wait for receipt
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            
            if receipt['status'] != 1:
                raise Exception("Transaction failed on-chain (reverted). Verify that parameters are supported by contract code structures.")

            # Parse the CreatorDeployed event
            logs = factory_contract.events.CreatorDeployed().process_receipt(receipt)
            if not logs:
                raise Exception("CreatorDeployed event not emitted.")
                
            token_contract = logs[0]['args']['tokenContract']
            logger.info(f"Creator deployed successfully at: {token_contract}")
            
            return token_contract
        except Exception as e:
            logger.error(f"Failed to deploy contract: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to deploy creator contract: {str(e)}")
    @staticmethod
    def get_creator_contract(address: str):
        from app.config import creator_abi
        return w3.eth.contract(address=w3.to_checksum_address(address), abi=creator_abi)

    @staticmethod
    def get_buy_quote(contract_address: str, amount: int) -> dict:
        contract = Web3Service.get_creator_contract(contract_address)
        try:
            # getBuyQuote(amount) returns (totalCost, fee) as a tuple
            total_cost, fee = contract.functions.getBuyQuote(amount).call()
            return {"total_cost": total_cost, "fee": fee, "price_without_fee": total_cost - fee}
        except Exception as e:
            logger.error(f"Failed to get buy quote: {e}")
            raise HTTPException(status_code=400, detail="Failed to calculate buy quote.")

    @staticmethod
    def get_sell_quote(contract_address: str, amount: int) -> dict:
        contract = Web3Service.get_creator_contract(contract_address)
        try:
            # Prevent Solidity Arithmetic Underflow (Panic 0x11) if supply is 0
            current_supply = contract.functions.currentSupply().call()
            if current_supply < amount:
                raise ValueError("Insufficient total supply to sell.")
                
            # getSellQuote(amount) returns (totalReturn, fee) as a tuple
            total_return, fee = contract.functions.getSellQuote(amount).call()
            return {"total_return": total_return, "fee": fee, "net": total_return - fee}
        except ValueError as ve:
            logger.error(f"Cannot get sell quote: {ve}")
            raise HTTPException(status_code=400, detail=str(ve))
        except Exception as e:
            logger.error(f"Failed to get sell quote: {e}")
            raise HTTPException(status_code=400, detail="Failed to calculate sell quote. Ensure the contract has enough supply.")
