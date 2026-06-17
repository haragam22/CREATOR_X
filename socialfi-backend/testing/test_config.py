from app.config import w3, factory_contract, usdc_contract, oracle_account, settings

def test_web3_connection():
    print("Testing Web3 Initialization...")
    
    # 1. Test RPC Connection
    is_connected = w3.is_connected()
    print(f"[*] Base Sepolia RPC Connected: {is_connected}")
    if is_connected:
        print(f"[*] Current Block Number: {w3.eth.block_number}")
        
    # 2. Test Factory Contract 
    print(f"\n[*] Factory Contract Address: {factory_contract.address}")
    try:
        # Call a view function from the Factory (getCreatorCount)
        creator_count = factory_contract.functions.getCreatorCount().call()
        print(f"[*] Factory getCreatorCount(): {creator_count}")
    except Exception as e:
        print(f"[!] Error calling Factory contract: {e}")
        
    # 3. Test USDC Contract
    print(f"\n[*] USDC Contract Address: {usdc_contract.address}")
    
    # 4. Test Oracle Account
    print(f"\n[*] Oracle Wallet Loaded Successfully")
    print(f"[*] Oracle Wallet Address: {oracle_account.address}")
    
if __name__ == "__main__":
    test_web3_connection()
