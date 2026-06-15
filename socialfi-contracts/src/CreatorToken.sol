// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC1155/ERC1155.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";

interface ISocialFiFactory {
    function isMarketOpen() external view returns (bool);
}

contract CreatorToken is ERC1155 {
    uint256 constant UPPER_BOUND_BPS  = 11000;   // +10%
    uint256 constant LOWER_BOUND_BPS  = 9000;    // -10%
    uint256 constant TOTAL_FEE_BPS    = 100;     // 1%
    uint256 constant CREATOR_FEE_BPS  = 60;      // 0.6%
    uint256 constant PROTOCOL_FEE_BPS = 40;      // 0.4%
    uint256 constant TOKEN_ID         = 1;       // single tier per creator

    uint256 public creatorId;
    address public creatorWallet;
    uint8 public tier;                  // 0/1/2
    uint256 public basePrice;           // micro-USDC
    uint256 public kScaled;             // k × 1e9
    uint256 public currentSupply;
    uint256 public aiModifierBps;       // 10000 = 1.0, init to 10000
    uint256 public creatorFeeBalance;   // internal ledger, micro-USDC
    uint256 public sessionOpeningPrice;
    bool public isSessionActive;
    bool public marketOpen;
    address public usdcAddress;
    address public oracleAddress;       // backend wallet
    address public treasuryAddress;
    uint256 public nextOpenTime;        // unix timestamp

    address public factoryAddress;

    event PassBought(
        address indexed buyer,
        uint256 amount,
        uint256 pricePerToken,
        uint256 totalCost,
        uint256 newSupply,
        uint256 timestamp
    );

    event PassSold(
        address indexed seller,
        uint256 amount,
        uint256 pricePerToken,
        uint256 totalReturn,
        uint256 newSupply,
        uint256 timestamp
    );

    event SentimentUpdated(
        uint256 newModifierBps,
        uint256 timestamp
    );

    event CreatorWithdraw(
        address indexed creator,
        uint256 amount
    );

    event PriceChanged(
        uint256 indexed creatorId,
        uint256 newPrice,
        uint256 timestamp
    );

    constructor(
        uint256 _creatorId,
        address _creatorWallet,
        uint8 _tier,
        uint256 _basePrice,
        uint256 _kScaled,
        address _usdcAddress,
        address _oracleAddress,
        address _treasuryAddress,
        address _factoryAddress
    ) ERC1155("") {
        creatorId = _creatorId;
        creatorWallet = _creatorWallet;
        tier = _tier;
        basePrice = _basePrice;
        kScaled = _kScaled;
        usdcAddress = _usdcAddress;
        oracleAddress = _oracleAddress;
        treasuryAddress = _treasuryAddress;
        factoryAddress = _factoryAddress;
        aiModifierBps = 10000;
        nextOpenTime = block.timestamp;
    }

    function _calcPrice(uint256 supply) internal view returns (uint256) {
        uint256 curve = (kScaled * supply * supply) / 1e9;
        return ((curve + basePrice) * aiModifierBps) / 10000;
    }

    function getCurrentPrice() external view returns (uint256) {
        return _calcPrice(currentSupply);
    }

    function getBuyQuote(uint256 amount) public view returns (uint256 totalCost, uint256 fee) {
        uint256 sumPrice = 0;
        for (uint256 i = 0; i < amount; i++) {
            sumPrice += _calcPrice(currentSupply + i);
        }
        fee = (sumPrice * TOTAL_FEE_BPS) / 10000;
        totalCost = sumPrice + fee;
    }

    function getSellQuote(uint256 amount) public view returns (uint256 totalReturn, uint256 fee) {
        uint256 sumPrice = 0;
        for (uint256 i = 1; i <= amount; i++) {
            sumPrice += _calcPrice(currentSupply - i);
        }
        fee = (sumPrice * TOTAL_FEE_BPS) / 10000;
        totalReturn = sumPrice - fee;
    }

    function buyPass(uint256 amount) external {
        bool isFactoryMarketOpen = ISocialFiFactory(factoryAddress).isMarketOpen();
        require(isFactoryMarketOpen, "Market: closed");
        require(isSessionActive, "Session: not active");

        (uint256 totalCost, uint256 fee) = getBuyQuote(amount);
        uint256 sumPrice = totalCost - fee;

        uint256 newPrice = _calcPrice(currentSupply + amount);
        (uint256 upper, uint256 lower) = getCircuitBreakerBounds();
        require(newPrice <= upper && newPrice >= lower, "CircuitBreaker: bounds exceeded");

        IERC20(usdcAddress).transferFrom(msg.sender, address(this), totalCost);
        
        uint256 creatorShare = (sumPrice * CREATOR_FEE_BPS) / 10000;
        uint256 protocolShare = (sumPrice * PROTOCOL_FEE_BPS) / 10000;
        
        creatorFeeBalance += creatorShare;
        IERC20(usdcAddress).transfer(treasuryAddress, protocolShare);
        
        currentSupply += amount;
        _mint(msg.sender, TOKEN_ID, amount, "");
        
        uint256 pricePerToken = amount > 0 ? sumPrice / amount : 0;
        emit PassBought(msg.sender, amount, pricePerToken, totalCost, currentSupply, block.timestamp);
        emit PriceChanged(creatorId, newPrice, block.timestamp);
    }

    function sellPass(uint256 amount) external {
        bool isFactoryMarketOpen = ISocialFiFactory(factoryAddress).isMarketOpen();
        require(isFactoryMarketOpen, "Market: closed");
        require(isSessionActive, "Session: not active");

        require(balanceOf(msg.sender, TOKEN_ID) >= amount, "Insufficient balance");

        (uint256 totalReturn, uint256 fee) = getSellQuote(amount);
        uint256 sumPrice = totalReturn + fee;

        uint256 newPrice = _calcPrice(currentSupply - amount);
        (uint256 upper, uint256 lower) = getCircuitBreakerBounds();
        require(newPrice <= upper && newPrice >= lower, "CircuitBreaker: bounds exceeded");

        _burn(msg.sender, TOKEN_ID, amount);
        currentSupply -= amount;
        
        uint256 creatorShare = (sumPrice * CREATOR_FEE_BPS) / 10000;
        uint256 protocolShare = (sumPrice * PROTOCOL_FEE_BPS) / 10000;
        
        creatorFeeBalance += creatorShare;
        
        IERC20(usdcAddress).transfer(treasuryAddress, protocolShare);
        IERC20(usdcAddress).transfer(msg.sender, totalReturn);

        uint256 pricePerToken = amount > 0 ? sumPrice / amount : 0;
        emit PassSold(msg.sender, amount, pricePerToken, totalReturn, currentSupply, block.timestamp);
        emit PriceChanged(creatorId, newPrice, block.timestamp);
    }

    function updateSentimentModifier(uint256 newModifierBps) external {
        require(msg.sender == oracleAddress, "Not oracle");
        require(newModifierBps >= 5000 && newModifierBps <= 15000, "Modifier out of bounds");
        aiModifierBps = newModifierBps;
        emit SentimentUpdated(newModifierBps, block.timestamp);
    }

    function openSession() external {
        require(block.timestamp >= nextOpenTime, "Too early to open session");
        require(!isSessionActive, "Session already active");
        sessionOpeningPrice = _calcPrice(currentSupply);
        isSessionActive = true;
        
        // Approximate scheduling: next open time is set by closeSession
        // or we just move it forward 8 hours to be safe.
        // For actual precise scheduling, it relies on oracle or precise math.
        nextOpenTime = block.timestamp + 8 hours;
    }

    function closeSession() external {
        require(msg.sender == oracleAddress, "Not oracle"); // Or block.timestamp >= sessionEndTime
        isSessionActive = false;
    }

    function creatorWithdraw() external {
        require(msg.sender == creatorWallet, "Not creator");
        uint256 amount = creatorFeeBalance;
        require(amount > 0, "No balance to withdraw");
        creatorFeeBalance = 0;
        IERC20(usdcAddress).transfer(creatorWallet, amount);
        emit CreatorWithdraw(msg.sender, amount);
    }

    function getCircuitBreakerBounds() public view returns (uint256 upper, uint256 lower) {
        // If session just opened and supply is 0, sessionOpeningPrice might be very small.
        upper = (sessionOpeningPrice * UPPER_BOUND_BPS) / 10000;
        lower = (sessionOpeningPrice * LOWER_BOUND_BPS) / 10000;
    }
}
