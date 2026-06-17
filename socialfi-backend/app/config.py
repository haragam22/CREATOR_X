import os
import json
from pathlib import Path
from pydantic_settings import BaseSettings
from web3 import Web3
from eth_account import Account

class Settings(BaseSettings):
    database_url: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./socialfi.db")
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379")
    
    backend_wallet_private_key: str = os.getenv("BACKEND_WALLET_PRIVATE_KEY", "0x0000000000000000000000000000000000000000000000000000000000000001")
    factory_contract_address: str = os.getenv("FACTORY_CONTRACT_ADDRESS", "0x8a502ad779b0153da45f4862f3599adfb034a03e")
    usdc_contract_address: str = os.getenv("USDC_CONTRACT_ADDRESS", "0x036CbD53842c5426634e7929541eC2318f3dCF7e")
    protocol_treasury_address: str = os.getenv("PROTOCOL_TREASURY_ADDRESS", "0x1a4B6a71a85F0cE39d1C4Ea31820BdEC6cB42749")
    
    base_sepolia_rpc: str = os.getenv("BASE_SEPOLIA_RPC", "https://sepolia.base.org")
    
    google_client_id: str = os.getenv("GOOGLE_CLIENT_ID", "dummy")
    google_client_secret: str = os.getenv("GOOGLE_CLIENT_SECRET", "dummy")
    jwt_secret: str = os.getenv("JWT_SECRET", "super-secret-default-key-for-local-dev")
    
    youtube_api_key: str = os.getenv("YOUTUBE_API_KEY", "dummy")
    
    celery_broker_url: str = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    celery_result_backend: str = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

    class Config:
        env_file = ".env"

settings = Settings()

# Init Web3
w3 = Web3(Web3.HTTPProvider(settings.base_sepolia_rpc))

# Load ABIs
BASE_DIR = Path(__file__).resolve().parent
with open(BASE_DIR / "abis" / "SocialFiFactory.json", "r") as f:
    factory_abi = json.load(f)["abi"]

with open(BASE_DIR / "abis" / "CreatorToken.json", "r") as f:
    creator_abi = json.load(f)["abi"]

with open(BASE_DIR / "abis" / "erc20.json", "r") as f:
    usdc_abi = json.load(f)

# Factory contract instance
factory_contract = w3.eth.contract(
    address=w3.to_checksum_address(settings.factory_contract_address),
    abi=factory_abi
)

usdc_contract = w3.eth.contract(
    address=w3.to_checksum_address(settings.usdc_contract_address),
    abi=usdc_abi
)

# Load backend Oracle Wallet
oracle_account = Account.from_key(settings.backend_wallet_private_key)
