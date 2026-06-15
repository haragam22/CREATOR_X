# SocialFi Creator Token & Fan Pass Marketplace
## TECHNICAL.md — Architecture, Contracts, APIs, Schemas

> **This is the single source of truth. Both HAR and GARV must implement against this document. Nothing changes without mutual agreement.**

---

## 1. System Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                  Flutter Mobile App                      │
│  WalletConnect v2 │ TradingView Charts │ REST + WS       │
└──────────┬────────────────────────┬─────────────────────┘
           │ REST/WebSocket         │ WalletConnect Deep Link
           ▼                        ▼
┌─────────────────────┐    ┌─────────────────────────┐
│   FastAPI Backend   │    │  MetaMask / Trust Wallet │
│  + Celery + Redis   │    │  (User's Mobile Wallet)  │
└──────┬──────────────┘    └──────────────────────────┘
       │ web3.py                    │ Signs tx
       │ Oracle writes              ▼
       ▼                   ┌─────────────────────────┐
┌─────────────────────┐    │   Base Sepolia Testnet   │
│   PostgreSQL DB     │    │                          │
│  (OHLC + metadata)  │    │  SocialFiFactory.sol     │
└─────────────────────┘    │  CreatorToken.sol (N×)   │
                           └─────────────────────────┘
```

---

## 2. Smart Contracts (LOCKED — DO NOT CHANGE WITHOUT BOTH AGREEING)

### 2.1 Network Config
- **Network:** Base Sepolia Testnet
- **Chain ID:** 84532
- **Currency:** USDC (6 decimals) — testnet USDC from Circle faucet
- **Finality:** ~2 seconds
- **Framework:** Foundry (preferred) or Hardhat

### 2.2 Solidity Fixed-Point Math Convention
Solidity has no floats. All USDC amounts are in **micro-USDC (6 decimal places)**:
- `1 USDC = 1_000_000` (1e6)
- `AI_Modifier` stored as **basis points**: `10000 = 1.0`, `5000 = 0.5`, `15000 = 1.5`
- `k` stored as **scaled integer** (see Section 2.5)

### 2.3 SocialFiFactory.sol

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface ISocialFiFactory {
    
    // Events
    event CreatorDeployed(
        uint256 indexed creatorId,
        address indexed tokenContract,
        address indexed creatorWallet,
        uint8 tier  // 0=Micro, 1=Mid, 2=Star
    );

    // State-changing functions
    function deployCreator(
        address creatorWallet,    // creator's EOA
        uint8 tier,               // 0, 1, or 2
        uint256 basePrice,        // in micro-USDC (6 decimals)
        uint256 kScaled           // k × 1e9 to avoid precision loss
    ) external returns (uint256 creatorId, address tokenContract);
    
    // View functions
    function getCreatorContract(uint256 creatorId) 
        external view returns (address);
    
    function getCreatorCount() 
        external view returns (uint256);
    
    // Admin
    function setMarketOpen(bool open) external;  // only ORACLE_ROLE
    function isMarketOpen() external view returns (bool);
}
```

### 2.4 CreatorToken.sol (ERC-1155)

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface ICreatorToken {

    // ─── Events ───────────────────────────────────────────────

    event PassBought(
        address indexed buyer,
        uint256 amount,
        uint256 pricePerToken,   // micro-USDC
        uint256 totalCost,       // micro-USDC including fee
        uint256 newSupply,
        uint256 timestamp
    );

    event PassSold(
        address indexed seller,
        uint256 amount,
        uint256 pricePerToken,   // micro-USDC
        uint256 totalReturn,     // micro-USDC after fee
        uint256 newSupply,
        uint256 timestamp
    );

    event SentimentUpdated(
        uint256 newModifierBps,  // basis points, 10000 = 1.0
        uint256 timestamp
    );

    event CreatorWithdraw(
        address indexed creator,
        uint256 amount           // micro-USDC
    );

    event PriceChanged(
        uint256 indexed creatorId,
        uint256 newPrice,        // micro-USDC
        uint256 timestamp
    );

    // ─── State-Changing Functions ──────────────────────────────

    function buyPass(uint256 amount) external;
    // User must have approved USDC spend before calling
    // Reverts if: market closed, price > upperBound, slippage exceeded

    function sellPass(uint256 amount) external;
    // Reverts if: market closed, price < lowerBound

    function updateSentimentModifier(uint256 newModifierBps) external;
    // Only callable by ORACLE_ROLE (backend wallet)
    // newModifierBps: 5000–15000 (0.5–1.5)

    function creatorWithdraw() external;
    // Creator claims accumulated 0.6% fee balance

    function openSession() external;
    // Permissionless: anyone can call if block.timestamp >= nextOpenTime && !sessionActive
    // Records sessionOpeningPrice for circuit breaker

    function closeSession() external;
    // Only ORACLE_ROLE or after session end time

    // ─── View Functions ────────────────────────────────────────

    function getCurrentPrice() external view returns (uint256);
    // Returns price for next 1 token in micro-USDC

    function getBuyQuote(uint256 amount) 
        external view returns (uint256 totalCost, uint256 fee);
    // Returns total USDC needed including 1% fee

    function getSellQuote(uint256 amount) 
        external view returns (uint256 totalReturn, uint256 fee);
    // Returns USDC returned after 1% fee

    function getCircuitBreakerBounds() 
        external view returns (uint256 upper, uint256 lower);

    function currentSupply() external view returns (uint256);
    function aiModifierBps() external view returns (uint256);
    function creatorFeeBalance() external view returns (uint256);
    function sessionOpeningPrice() external view returns (uint256);
    function isSessionActive() external view returns (bool);
}
```

### 2.5 Tier-Specific Contract Parameters (Pass to deployCreator)

| Tier | basePrice (micro-USDC) | kScaled (k × 1e9) | kActual |
|------|------------------------|-------------------|---------|
| Micro (0) | 600_000 | 8_000_000 | 0.008 |
| Mid (1) | 2_350_000 | 30_000_000 | 0.030 |
| Star (2) | 9_400_000 | 120_000_000 | 0.120 |

**Price formula in Solidity:**
```solidity
// Price in micro-USDC
function _calcPrice(uint256 supply) internal view returns (uint256) {
    uint256 curve = (kScaled * supply * supply) / 1e9;
    return (curve + basePrice) * aiModifierBps / 10000;
}
```

### 2.6 Fee Constants
```solidity
uint256 constant TOTAL_FEE_BPS = 100;       // 1% = 100 basis points
uint256 constant CREATOR_FEE_BPS = 60;      // 0.6%
uint256 constant PROTOCOL_FEE_BPS = 40;     // 0.4%
address constant PROTOCOL_TREASURY = 0x...;  // multi-sig, set at deploy
```

### 2.7 Circuit Breaker Constants
```solidity
uint256 constant UPPER_BOUND_BPS = 11000;   // 110% = +10%
uint256 constant LOWER_BOUND_BPS = 9000;    // 90%  = -10%

// In buyPass/sellPass:
uint256 upper = sessionOpeningPrice * UPPER_BOUND_BPS / 10000;
uint256 lower = sessionOpeningPrice * LOWER_BOUND_BPS / 10000;
require(newPrice <= upper && newPrice >= lower, "CircuitBreaker: bounds exceeded");
```

---

## 3. Database Schema (PostgreSQL)

```sql
-- Creator metadata
CREATE TABLE creators (
    id              SERIAL PRIMARY KEY,
    google_id       VARCHAR(255) UNIQUE NOT NULL,
    youtube_channel_id VARCHAR(255) UNIQUE NOT NULL,
    display_name    VARCHAR(255),
    wallet_address  VARCHAR(42) UNIQUE NOT NULL,
    token_contract  VARCHAR(42) UNIQUE,          -- null until deployed
    tier            SMALLINT NOT NULL,            -- 0/1/2
    base_price_usdc NUMERIC(18,6) NOT NULL,
    k_value         NUMERIC(18,9) NOT NULL,
    subscriber_count BIGINT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Raw on-chain transaction events (indexed from web3.py listener)
CREATE TABLE price_events (
    id              BIGSERIAL PRIMARY KEY,
    creator_id      INTEGER REFERENCES creators(id),
    event_type      VARCHAR(10) NOT NULL,        -- 'buy' | 'sell' | 'sentiment'
    price_usdc      NUMERIC(18,6) NOT NULL,
    supply          BIGINT NOT NULL,
    tx_hash         VARCHAR(66) UNIQUE NOT NULL,
    block_number    BIGINT NOT NULL,
    block_timestamp TIMESTAMPTZ NOT NULL
);

-- 5-minute OHLC candles (aggregated by Celery task)
CREATE TABLE candles_5m (
    id              BIGSERIAL PRIMARY KEY,
    creator_id      INTEGER REFERENCES creators(id),
    open_time       TIMESTAMPTZ NOT NULL,
    close_time      TIMESTAMPTZ NOT NULL,
    open_price      NUMERIC(18,6) NOT NULL,
    high_price      NUMERIC(18,6) NOT NULL,
    low_price       NUMERIC(18,6) NOT NULL,
    close_price     NUMERIC(18,6) NOT NULL,
    volume_tokens   BIGINT NOT NULL,
    UNIQUE(creator_id, open_time)
);

-- AI sentiment history
CREATE TABLE sentiment_history (
    id              BIGSERIAL PRIMARY KEY,
    creator_id      INTEGER REFERENCES creators(id),
    modifier_bps    INTEGER NOT NULL,            -- 5000–15000
    raw_score       NUMERIC(5,4),               -- raw DistilBERT score
    comment_sample  INTEGER,                    -- comments analyzed
    computed_at     TIMESTAMPTZ DEFAULT NOW(),
    tx_hash         VARCHAR(66)                 -- null if threshold not crossed
);

-- Indexes
CREATE INDEX idx_price_events_creator_time ON price_events(creator_id, block_timestamp);
CREATE INDEX idx_candles_creator_time ON candles_5m(creator_id, open_time);
```

---

## 4. FastAPI Endpoints (Locked Contract)

### Auth
```
POST   /auth/google          → {access_token, user_id, is_creator}
POST   /auth/link-wallet     → {wallet_address} → 200 OK
GET    /auth/me              → {user profile}
```

### Creators
```
POST   /creators/register           → Evaluate YouTube metrics, assign tier, deploy contract
GET    /creators                    → List all creators (with current price, AI modifier)
GET    /creators/{id}               → Creator detail + current price + supply
GET    /creators/{id}/candles?tf=5m → OHLC array [{time, open, high, low, close}]
GET    /creators/{id}/quote/buy?amount=N   → {totalCost, fee, pricePerToken}
GET    /creators/{id}/quote/sell?amount=N  → {totalReturn, fee, pricePerToken}
GET    /creators/{id}/sentiment     → {modifierBps, rawScore, lastUpdated}
```

### Market
```
GET    /market/status        → {isOpen, sessionStart, sessionEnd, nextOpen}
POST   /market/open          → (internal/cron, calls openSession() on all contracts)
POST   /market/close         → (internal/cron)
```

### User Portfolio
```
GET    /portfolio/{wallet}   → All tokens held + current values
```

### Creator Dashboard (authenticated)
```
GET    /dashboard/earnings          → {totalAccrued, withdrawable}
POST   /dashboard/withdraw          → Trigger creatorWithdraw() via web3.py
GET    /dashboard/transactions      → Fee events for this creator
```

---

## 5. WebSocket Events

**Endpoint:** `ws://host/ws/market`

**Subscription message:**
```json
{ "action": "subscribe", "creator_id": 42 }
```

**Server pushes:**
```json
// New completed candle (every 5 minutes)
{ "type": "candle", "creator_id": 42, "data": {
    "time": 1718000000, "open": 2.38, "high": 2.65, "low": 2.31, "close": 2.55
}}

// Live price tick (every buy/sell event)
{ "type": "tick", "creator_id": 42, "data": {
    "price": 2.55, "supply": 14, "event": "buy", "timestamp": 1718000000
}}

// Sentiment update
{ "type": "sentiment", "creator_id": 42, "data": {
    "modifierBps": 11500, "timestamp": 1718000000
}}

// Market open/close
{ "type": "market_status", "data": { "isOpen": true, "sessionEnd": 1718014800 }}
```

---

## 6. Celery Task Map

```
celery_app
├── tasks.sentiment
│   ├── fetch_youtube_comments(creator_id)     → every 30 min per creator
│   ├── run_nlp_pipeline(creator_id, comments) → DistilBERT sentiment score
│   └── maybe_update_on_chain(creator_id, new_score) → only if Δ > 5% threshold
│
├── tasks.market
│   ├── open_market_session()   → Celery beat: 10:00 AM IST, 6:00 PM IST
│   └── close_market_session()  → Celery beat: 2:00 PM IST, 10:00 PM IST
│
├── tasks.candles
│   └── aggregate_5m_candles()  → every 5 minutes, queries price_events, writes candles_5m
│
└── tasks.events
    └── event_listener_daemon() → persistent web3.py filter on PriceChanged + PassBought + PassSold
        → writes to price_events table
        → pushes tick to WebSocket broadcast
```

**Celery Beat Schedule (IST = UTC+5:30):**
```python
CELERYBEAT_SCHEDULE = {
    'open-morning':  {'task': 'tasks.market.open_market_session',  'schedule': crontab(hour=4, minute=30)},   # 10:00 IST = 04:30 UTC
    'close-morning': {'task': 'tasks.market.close_market_session', 'schedule': crontab(hour=8, minute=30)},   # 14:00 IST = 08:30 UTC
    'open-evening':  {'task': 'tasks.market.open_market_session',  'schedule': crontab(hour=12, minute=30)},  # 18:00 IST = 12:30 UTC
    'close-evening': {'task': 'tasks.market.close_market_session', 'schedule': crontab(hour=16, minute=30)},  # 22:00 IST = 16:30 UTC
    'candles':       {'task': 'tasks.candles.aggregate_5m_candles','schedule': crontab(minute='*/5')},
    'sentiment-all': {'task': 'tasks.sentiment.run_all_creators',  'schedule': crontab(minute='*/30')},
}
```

**Cron misfire recovery:** `openSession()` on the contract is permissionless — if Celery misses the scheduled call, a retry loop in the market open task fires every 2 minutes for 10 minutes post-scheduled time. If all retries fail, the contract remains closed but no funds are lost.

---

## 7. YouTube API Strategy

- **Quota:** 10,000 units/day (free tier)
- **Comment thread list:** 1 unit per page of 100 comments
- **Strategy:** Fetch 100 most recent comments per creator per cycle = 1 unit/creator/cycle
- **Cycle:** Every 30 minutes per creator
- **Cap:** Max 10 demo creators → 10 units/cycle × 48 cycles = **480 units/day** (well within limit)
- **Cache:** Store last fetched comment IDs in Redis; only send new comments to NLP pipeline
- **Batch:** Use `YouTubeDataAPI.comments().list()` with `part=snippet`, filter by `videoId` of latest video

---

## 8. AI Sentiment Pipeline

```python
# Model: distilbert-base-uncased-finetuned-sst-2-english
# Input: list of comment strings
# Output: AI_Modifier in basis points (5000–15000)

def compute_modifier(comments: list[str]) -> int:
    results = sentiment_pipeline(comments, truncation=True, max_length=512)
    
    positive_scores = [r['score'] for r in results if r['label'] == 'POSITIVE']
    negative_scores = [r['score'] for r in results if r['label'] == 'NEGATIVE']
    
    avg_positive = mean(positive_scores) if positive_scores else 0.5
    avg_negative = mean(negative_scores) if negative_scores else 0.5
    
    # Net sentiment: -1.0 to +1.0
    net = avg_positive - avg_negative
    
    # Map to modifier: net=-1 → 0.5 (5000 bps), net=0 → 1.0 (10000 bps), net=+1 → 1.5 (15000 bps)
    modifier = 1.0 + (net * 0.5)
    return int(modifier * 10000)  # basis points

# Only write on-chain if change > 5% from current stored value
def maybe_update_on_chain(creator_id, new_bps, current_bps):
    delta = abs(new_bps - current_bps) / current_bps
    if delta >= 0.05:
        contract.updateSentimentModifier(new_bps)  # gas saved otherwise
```

---

## 9. Environment Variables

```env
# Backend
DATABASE_URL=postgresql://user:pass@localhost/socialfi
REDIS_URL=redis://localhost:6379
BACKEND_WALLET_PRIVATE_KEY=0x...        # Oracle wallet — never commit this
FACTORY_CONTRACT_ADDRESS=0x...
USDC_CONTRACT_ADDRESS=0x...             # Base Sepolia USDC
PROTOCOL_TREASURY_ADDRESS=0x...

# Google OAuth
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...

# YouTube
YOUTUBE_API_KEY=...

# Celery
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1
```

---

## 10. Demo Simulator Script (Testnet)

`demo_simulator.py` — pre-fund 5 test wallets, fire randomized transactions during demo:

```python
# Fires every 15–45 seconds during demo
# Randomly picks: buy or sell
# Randomly picks: 1–3 tokens
# Randomly picks: one of 3 demo creator contracts
# Uses 5 pre-funded test wallets with Base Sepolia ETH + USDC
# This generates real on-chain events → real OHLC candle movement in the Flutter app
```
