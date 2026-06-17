import logging
from app.config import w3, settings
from app.services.web3_service import Web3Service

logger = logging.getLogger(__name__)

class OracleService:
    @staticmethod
    def update_sentiment(contract_address: str, new_bps: int) -> str:
        """
        Calls updateSentimentModifier(new_bps) on the CreatorToken contract
        using the backend Oracle wallet.
        """
        logger.info(f"Oracle: Updating sentiment for {contract_address} to {new_bps} bps")
        contract = Web3Service.get_creator_contract(contract_address)
        
        tx = contract.functions.updateSentimentModifier(new_bps).build_transaction({
            'from': w3.eth.account.from_key(settings.backend_wallet_private_key).address,
            'nonce': w3.eth.get_transaction_count(w3.eth.account.from_key(settings.backend_wallet_private_key).address),
            'gas': 3000000,
            'gasPrice': w3.eth.gas_price
        })
        
        signed_tx = w3.eth.account.sign_transaction(tx, private_key=settings.backend_wallet_private_key)
        try:
            raw_tx = signed_tx.raw_transaction
        except AttributeError:
            raw_tx = signed_tx.rawTransaction
            
        tx_hash = w3.eth.send_raw_transaction(raw_tx)
        logger.info(f"Oracle tx sent! Hash: {tx_hash.hex()}")
        
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        if receipt.status != 1:
            logger.error(f"Oracle tx failed. Receipt: {receipt}")
            raise Exception("Oracle tx failed")
            
        logger.info(f"Oracle tx confirmed!")
        return tx_hash.hex()
