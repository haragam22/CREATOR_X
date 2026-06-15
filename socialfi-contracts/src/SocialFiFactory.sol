// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./CreatorToken.sol";

contract SocialFiFactory {
    mapping(uint256 => address) public creatorContracts;
    uint256 public creatorCount;
    bool public isMarketOpen;
    address public oracle;              // backend wallet — set in constructor
    address public usdcAddress;
    address public treasuryAddress;

    event CreatorDeployed(
        uint256 indexed creatorId,
        address indexed tokenContract,
        address indexed creatorWallet,
        uint8 tier  // 0=Micro, 1=Mid, 2=Star
    );

    constructor(address _oracle, address _usdcAddress, address _treasuryAddress) {
        oracle = _oracle;
        usdcAddress = _usdcAddress;
        treasuryAddress = _treasuryAddress;
    }

    function deployCreator(
        address creatorWallet,
        uint8 tier,
        uint256 basePrice,
        uint256 kScaled
    ) external returns (uint256 creatorId, address tokenContract) {
        require(msg.sender == oracle, "Not oracle");
        creatorId = ++creatorCount;
        CreatorToken token = new CreatorToken(
            creatorId, creatorWallet, tier, basePrice, kScaled,
            usdcAddress, oracle, treasuryAddress, address(this)
        );
        creatorContracts[creatorId] = address(token);
        emit CreatorDeployed(creatorId, address(token), creatorWallet, tier);
        return (creatorId, address(token));
    }

    function setMarketOpen(bool open) external {
        require(msg.sender == oracle, "Not oracle");
        isMarketOpen = open;
    }

    function getCreatorContract(uint256 creatorId) external view returns (address) {
        return creatorContracts[creatorId];
    }

    function getCreatorCount() external view returns (uint256) {
        return creatorCount;
    }
}
