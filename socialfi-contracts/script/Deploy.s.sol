// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Script.sol";
import "../src/SocialFiFactory.sol";
import "../src/CreatorToken.sol";

contract Deploy is Script {
    function run() external {
        uint256 deployerPrivateKey = vm.envUint("DEPLOYER_PRIVATE_KEY");
        address usdcAddress = vm.envAddress("USDC_ADDRESS");
        address treasuryAddress = vm.envAddress("PROTOCOL_TREASURY");
        
        vm.startBroadcast(deployerPrivateKey);
        
        address oracle = vm.addr(deployerPrivateKey); // For testnet, deployer is oracle

        SocialFiFactory factory = new SocialFiFactory(oracle, usdcAddress, treasuryAddress);
        
        // Open the market globally
        factory.setMarketOpen(true);

        // Demo creators
        // 1. demo_micro: tier=0, basePrice=600_000, kScaled=8_000_000
        (uint256 microId, address microAddress) = factory.deployCreator(oracle, 0, 600_000, 8_000_000);
        
        // 2. demo_mid: tier=1, basePrice=2_350_000, kScaled=30_000_000
        (uint256 midId, address midAddress) = factory.deployCreator(oracle, 1, 2_350_000, 30_000_000);
        
        // 3. demo_star: tier=2, basePrice=9_400_000, kScaled=120_000_000
        (uint256 starId, address starAddress) = factory.deployCreator(oracle, 2, 9_400_000, 120_000_000);

        console.log("Factory Address:", address(factory));
        console.log("Demo Micro Address:", microAddress);
        console.log("Demo Mid Address:", midAddress);
        console.log("Demo Star Address:", starAddress);

        vm.stopBroadcast();
    }
}