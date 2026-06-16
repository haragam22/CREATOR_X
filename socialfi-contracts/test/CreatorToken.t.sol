// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "../src/CreatorToken.sol";
import "../src/SocialFiFactory.sol";
import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

contract MockUSDC is ERC20 {
    constructor() ERC20("Mock USDC", "USDC") {}

    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }
}

contract CreatorTokenTest is Test {
    MockUSDC usdc;
    SocialFiFactory factory;
    CreatorToken token;

    address oracle = address(0x111);
    address treasury = address(0x222);
    address creatorWallet = address(0x333);
    address buyer = address(0x444);
    address seller = address(0x555);

    uint8 tier = 1; // Mid
    uint256 basePrice = 2_350_000; // 2.35 USDC
    uint256 kScaled = 30_000_000;

    function setUp() public {
        usdc = new MockUSDC();
        
        factory = new SocialFiFactory(oracle, address(usdc), treasury);

        vm.prank(oracle);
        factory.setMarketOpen(true);

        vm.prank(oracle);
        (uint256 creatorId, address tokenAddr) = factory.deployCreator(creatorWallet, tier, basePrice, kScaled);
        token = CreatorToken(tokenAddr);

        // Fund buyer and seller
        usdc.mint(buyer, 10000 * 1e6);
        usdc.mint(seller, 10000 * 1e6);
        
        vm.prank(buyer);
        usdc.approve(address(token), type(uint256).max);

        vm.prank(seller);
        usdc.approve(address(token), type(uint256).max);

        // Open session
        token.openSession();
    }

    function testBuyAtSupplyZero() public {
        uint256 price = token.getCurrentPrice();
        assertEq(price, basePrice); // Since AI modifier is 10000 (1.0) and supply is 0

        vm.prank(buyer);
        token.buyPass(1);

        assertEq(token.currentSupply(), 1);
        assertEq(token.balanceOf(buyer, 1), 1);
    }

    function testPriceIncreasesAfterBuys() public {
        uint256 prevPrice = token.getCurrentPrice();
        
        for (uint256 i = 0; i < 2; i++) {
            vm.prank(buyer);
            token.buyPass(1);
            
            uint256 newPrice = token.getCurrentPrice();
            assertTrue(newPrice > prevPrice);
            prevPrice = newPrice;
        }
    }

    function testCircuitBreakerUpperReverts() public {
        // AI modifier jumps drastically, increasing price
        vm.prank(oracle);
        token.updateSentimentModifier(15000); // 1.5x
        
        // Price should now be out of bounds for buying
        vm.expectRevert("CircuitBreaker: bounds exceeded");
        vm.prank(buyer);
        token.buyPass(1);
    }

    function testCircuitBreakerLowerReverts() public {
        // Buy one first to have a supply
        vm.prank(buyer);
        token.buyPass(1);

        // Drop the sentiment modifier
        vm.prank(oracle);
        token.updateSentimentModifier(5000); // 0.5x

        // Sell pass should fail due to lower bound
        vm.expectRevert("CircuitBreaker: bounds exceeded");
        vm.prank(buyer);
        token.sellPass(1);
    }

    function testSellReturnsCorrectUSDC() public {
        // Buy 2
        vm.prank(buyer);
        token.buyPass(2);

        uint256 buyerBalanceBefore = usdc.balanceOf(buyer);
        
        (uint256 expectedReturn, ) = token.getSellQuote(1);

        vm.prank(buyer);
        token.sellPass(1);

        uint256 buyerBalanceAfter = usdc.balanceOf(buyer);
        
        assertEq(buyerBalanceAfter - buyerBalanceBefore, expectedReturn);
        assertEq(token.balanceOf(buyer, 1), 1);
    }

    function testSentimentModifierChangesPrice() public {
        uint256 priceNeutral = token.getCurrentPrice();
        
        vm.prank(oracle);
        token.updateSentimentModifier(15000); // 1.5x

        uint256 priceBullish = token.getCurrentPrice();
        assertEq(priceBullish, (priceNeutral * 15000) / 10000);
    }

    function testMarketClosedReverts() public {
        vm.prank(oracle);
        factory.setMarketOpen(false);

        vm.expectRevert("Market: closed");
        vm.prank(buyer);
        token.buyPass(1);
    }

    function testOnlyOracleCanUpdateSentiment() public {
        vm.expectRevert("Not oracle");
        vm.prank(buyer);
        token.updateSentimentModifier(15000);
    }

    function testCreatorWithdraw() public {
        // Buy some tokens
        vm.prank(buyer);
        token.buyPass(2);

        uint256 feeBalance = token.creatorFeeBalance();
        assertTrue(feeBalance > 0);

        uint256 walletBalanceBefore = usdc.balanceOf(creatorWallet);
        
        vm.prank(creatorWallet);
        token.creatorWithdraw();

        uint256 walletBalanceAfter = usdc.balanceOf(creatorWallet);
        assertEq(walletBalanceAfter - walletBalanceBefore, feeBalance);
        assertEq(token.creatorFeeBalance(), 0);
    }
}