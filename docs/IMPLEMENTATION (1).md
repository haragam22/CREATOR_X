# SocialFi Creator Token & Fan Pass Marketplace
## IMPLEMENTATION_FULL.md — Complete Phased Build Plan

> **Owner Tags:** `[HAR]` = Haragam (FastAPI/Python Backend + Solidity logic) | `[GARV]` = Garv (Flutter Frontend + Solidity structure/deploy)
>
> **Core Rule:** Phase 1 (Solidity) must be 100% done and ABI exported before Phase 2 starts. ABI is frozen after Phase 1. No exceptions — GARV must not build wallet/transaction UI until the ABI is locked.
>
> **Reference:** All interfaces, schemas, addresses, and formulas are in `TECHNICAL.md`. This file is build order only.

---

## PHASE 1 — Solidity Contracts
### ⏱ Estimated: 5–6 hours | Do this first, in the same room/call

Phase 1 is split so HAR owns the business logic (math, fees, access control) and GARV owns the project structure, tests, and deployment. HAR writes contracts → GARV tests and deploys. This ordering means GARV can set up Foundry and write test scaffolding while HAR is still writing contract logic — minimal blocking.

---

### 1.1 — Foundry Project Setup `[GARV]`

GARV sets this up while HAR starts reading `TECHNICAL.md §2` to plan contract logic.

```bash
curl -L https://foundry.paradigm.xyz | bash
foundryup
forge init socialfi-contracts && cd socialfi-contracts
forge install OpenZeppelin/openzeppelin-contracts
```

Create `.env` in `socialfi-contracts/`:
```env
DEPLOYER_PRIVATE_KEY=0x...          # A fresh wallet funded with Base Sepolia ETH
BASE_SEPOLIA_RPC=https://sepolia.base.org
BASESCAN_API_KEY=...
USDC_ADDRESS=0x036CbD53842c5426634e7929541eC2318f3dCF7e
PROTOCOL_TREASURY=0x...
```

Create stub files so HAR can start writing immediately:
```bash
touch src/CreatorToken.sol
touch src/SocialFiFactory.sol
touch test/CreatorToken.t.sol
touch script/Deploy.s.sol
```

---

### 1.2 — Write `CreatorToken.sol` `[HAR]`

File: `src/CreatorToken.sol`

HAR implements the full `ICreatorToken` interface from `TECHNICAL.md §2.4`. Build in this exact sub-order so GARV can start writing tests against the interface before the implementation is complete:

**1.2a — Storage + Constructor**
```solidity
// State variables needed:
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
bool public marketOpen;             // set by factory/oracle
address public usdcAddress;
address public oracleAddress;       // backend wallet
address public treasuryAddress;
uint256 public nextOpenTime;        // unix timestamp
```

**1.2b — Price Formula** (copy exactly from `TECHNICAL.md §2.5`)
```solidity
function _calcPrice(uint256 supply) internal view returns (uint256) {
    uint256 curve = (kScaled * supply * supply) / 1e9;
    return (curve + basePrice) * aiModifierBps / 10000;
}
```

**1.2c — `getBuyQuote` / `getSellQuote`**
Implement as view using `_calcPrice`. Sum prices for tokens from `supply` to `supply+amount` for buy. Reverse for sell. Apply 1% fee split (60 bps creator, 40 bps protocol).

**1.2d — `buyPass(uint256 amount)`**
- [ ] Revert if `!marketOpen` → `"Market: closed"`
- [ ] Revert if `!isSessionActive` → `"Session: not active"`
- [ ] Compute `totalCost` via `getBuyQuote`
- [ ] `IERC20(usdcAddress).transferFrom(msg.sender, address(this), totalCost)`
- [ ] Add `creatorShare` to `creatorFeeBalance`
- [ ] `IERC20(usdcAddress).transfer(treasuryAddress, protocolShare)`
- [ ] `currentSupply += amount`
- [ ] `_mint(msg.sender, TOKEN_ID, amount, "")`
- [ ] Compute new price → check circuit breaker (revert if breached)
- [ ] Emit `PassBought`, `PriceChanged`

**1.2e — `sellPass(uint256 amount)`**
Same pattern reversed: burn token, compute return, check lower bound, transfer USDC out minus fee.

**1.2f — `updateSentimentModifier(uint256 newModifierBps)`**
- [ ] `require(msg.sender == oracleAddress, "Not oracle")`
- [ ] Clamp: `require(newModifierBps >= 5000 && newModifierBps <= 15000)`
- [ ] Set `aiModifierBps = newModifierBps`
- [ ] Emit `SentimentUpdated`

**1.2g — `openSession()`**
- [ ] Permissionless — anyone can call
- [ ] `require(block.timestamp >= nextOpenTime && !isSessionActive)`
- [ ] `sessionOpeningPrice = _calcPrice(currentSupply)`
- [ ] `isSessionActive = true`
- [ ] Set `nextOpenTime` to next scheduled session

**1.2h — `closeSession()`**
- [ ] `require(msg.sender == oracleAddress || block.timestamp >= sessionEndTime)`
- [ ] `isSessionActive = false`

**1.2i — `creatorWithdraw()`**
- [ ] `require(msg.sender == creatorWallet)`
- [ ] Transfer `creatorFeeBalance` to `creatorWallet`
- [ ] Reset `creatorFeeBalance = 0`
- [ ] Emit `CreatorWithdraw`

**Constants at top of contract:**
```solidity
uint256 constant UPPER_BOUND_BPS  = 11000;   // +10%
uint256 constant LOWER_BOUND_BPS  = 9000;    // -10%
uint256 constant TOTAL_FEE_BPS    = 100;     // 1%
uint256 constant CREATOR_FEE_BPS  = 60;      // 0.6%
uint256 constant PROTOCOL_FEE_BPS = 40;      // 0.4%
uint256 constant TOKEN_ID         = 1;       // single tier per creator
```

---

### 1.3 — Write `SocialFiFactory.sol` `[HAR]`

File: `src/SocialFiFactory.sol`

```solidity
// Deploys CreatorToken instances, controls global market flag

mapping(uint256 => address) public creatorContracts;
uint256 public creatorCount;
bool public isMarketOpen;
address public oracle;              // backend wallet — set in constructor

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
        usdcAddress, oracle, treasuryAddress
    );
    creatorContracts[creatorId] = address(token);
    emit CreatorDeployed(creatorId, address(token), creatorWallet, tier);
    return (creatorId, address(token));
}

function setMarketOpen(bool open) external {
    require(msg.sender == oracle, "Not oracle");
    isMarketOpen = open;
    // Child contracts read marketOpen from factory via stored factory address
}

function getCreatorContract(uint256 creatorId) external view returns (address) {
    return creatorContracts[creatorId];
}

function getCreatorCount() external view returns (uint256) {
    return creatorCount;
}
```

> When HAR finishes 1.2 and 1.3, tell GARV. GARV then fills in the test bodies in 1.4.

---

### 1.4 — Write Tests `[GARV]`

File: `test/CreatorToken.t.sol`

GARV writes the test scaffolding (setUp, mock USDC, deploy helpers) while HAR writes the contracts. Once HAR signals contracts compile, GARV fills in the test bodies.

```bash
forge test -vvv
```

Required test cases — GARV writes all of these:
- [ ] `testBuyAtSupplyZero` — price equals `basePrice × aiModifier / 10000`
- [ ] `testPriceIncreasesAfterBuys` — 5 sequential buys, each `getCurrentPrice()` > previous
- [ ] `testCircuitBreakerUpperReverts` — manipulate supply so price hits 111% of session open → expect revert
- [ ] `testCircuitBreakerLowerReverts` — force price below 90% of session open → expect revert on sell
- [ ] `testSellReturnsCorrectUSDC` — buy 5 tokens then sell 3, assert USDC returned = expected minus 1% fee
- [ ] `testSentimentModifierChangesPrice` — set modifier to 15000, assert price is exactly 1.5× neutral price
- [ ] `testMarketClosedReverts` — call `buyPass` with `marketOpen = false` → expect revert `"Market: closed"`
- [ ] `testOnlyOracleCanUpdateSentiment` — call `updateSentimentModifier` from non-oracle address → expect revert
- [ ] `testCreatorWithdraw` — run buys, assert `creatorFeeBalance > 0`, call `creatorWithdraw`, assert USDC transferred and balance resets to 0

---

### 1.5 — Deploy Script + Deploy to Base Sepolia `[GARV]`

File: `script/Deploy.s.sol` — GARV writes the deploy script.

```bash
# Deploy factory
forge script script/Deploy.s.sol \
  --rpc-url $BASE_SEPOLIA_RPC \
  --broadcast \
  --private-key $DEPLOYER_PRIVATE_KEY

# Verify on Basescan
forge verify-contract $FACTORY_ADDRESS src/SocialFiFactory.sol:SocialFiFactory \
  --chain-id 84532 \
  --etherscan-api-key $BASESCAN_API_KEY
```

After factory is live, GARV calls `deployCreator()` 3 times with these exact params to create demo contracts:

| Demo Creator | Tier | basePrice (micro-USDC) | kScaled |
|---|---|---|---|
| demo_micro | 0 | 600_000 | 8_000_000 |
| demo_mid | 1 | 2_350_000 | 30_000_000 |
| demo_star | 2 | 9_400_000 | 120_000_000 |

GARV records all addresses and shares with HAR:
```
FACTORY_CONTRACT_ADDRESS=0x...
DEMO_MICRO_ADDRESS=0x...
DEMO_MID_ADDRESS=0x...
DEMO_STAR_ADDRESS=0x...
```

HAR writes these into `socialfi-backend/.env`.
GARV writes these into `lib/config/constants.dart`.

---

### 1.6 — Export ABI `[GARV]`

```bash
# After forge build:
cp out/CreatorToken.sol/CreatorToken.json ../socialfi-backend/app/abis/
cp out/SocialFiFactory.sol/SocialFiFactory.json ../socialfi-backend/app/abis/
# Also keep a copy in Flutter assets for WalletConnect tx construction
cp out/CreatorToken.sol/CreatorToken.json ../socialfi-app/assets/abis/
```

---

### ✅ Phase 1 Exit Criteria

HAR confirms:
- [ ] `CreatorToken.sol` compiles with no warnings
- [ ] `SocialFiFactory.sol` compiles with no warnings

GARV confirms:
- [ ] All 9 tests pass (`forge test -vvv`)
- [ ] Factory verified on Basescan
- [ ] 3 demo creator contracts live and verified
- [ ] ABI JSON files shared with HAR and stored in Flutter assets
- [ ] All 4 contract addresses written into both configs

**After this point: ABI is frozen. No Solidity changes without both agreeing.**

---
---

## PHASE 2A — FastAPI Backend `[HAR]`
### ⏱ Estimated: 8–10 hours | Runs fully parallel to GARV's Phase 2B

**Goal:** Running backend with all endpoints, Celery tasks, WebSocket, and demo simulator. HAR works on this entirely independently — GARV does not touch any of this.

---

### 2A.1 — Project Setup

```bash
mkdir socialfi-backend && cd socialfi-backend
python -m venv venv && source venv/bin/activate

pip install fastapi uvicorn[standard] celery redis web3 sqlalchemy asyncpg \
            google-auth google-auth-oauthlib httpx \
            transformers torch python-dotenv alembic psycopg2-binary \
            python-jose[cryptography] passlib
```

**Directory structure:**
```
socialfi-backend/
├── .env
├── requirements.txt
├── app/
│   ├── main.py
│   ├── config.py
│   ├── abis/
│   │   ├── CreatorToken.json        # from Phase 1
│   │   └── SocialFiFactory.json     # from Phase 1
│   ├── db/
│   │   ├── models.py
│   │   └── session.py
│   ├── routers/
│   │   ├── auth.py
│   │   ├── creators.py
│   │   ├── market.py
│   │   ├── portfolio.py
│   │   └── dashboard.py
│   ├── services/
│   │   ├── youtube.py
│   │   ├── web3_service.py
│   │   ├── sentiment.py
│   │   └── oracle.py
│   ├── tasks/
│   │   ├── celery_app.py
│   │   ├── sentiment_tasks.py
│   │   ├── market_tasks.py
│   │   ├── candle_tasks.py
│   │   └── event_listener.py
│   └── websocket/
│       └── manager.py
├── alembic/
│   └── versions/
└── demo_simulator.py
```

---

### 2A.2 — Step 1: Config + DB Setup

**`app/config.py`**
- [ ] Load all env vars from `.env` using `python-dotenv`
- [ ] Init `Web3` connection to Base Sepolia RPC
- [ ] Load Factory ABI from `app/abis/SocialFiFactory.json`, create `factory_contract` object
- [ ] Load CreatorToken ABI from `app/abis/CreatorToken.json` (used per-contract)
- [ ] Load USDC ABI (standard ERC-20), create `usdc_contract` object
- [ ] Load oracle wallet: `Account.from_key(BACKEND_WALLET_PRIVATE_KEY)`

**`app/db/models.py`**
Implement all 4 SQLAlchemy models matching `TECHNICAL.md §3` exactly:
- [ ] `Creator` — `id, google_id, youtube_channel_id, display_name, wallet_address, token_contract, tier, base_price_usdc, k_value, subscriber_count, created_at`
- [ ] `PriceEvent` — `id, creator_id, event_type, price_usdc, supply, tx_hash, block_number, block_timestamp`
- [ ] `Candle5m` — `id, creator_id, open_time, close_time, open_price, high_price, low_price, close_price, volume_tokens`
- [ ] `SentimentHistory` — `id, creator_id, modifier_bps, raw_score, comment_sample, computed_at, tx_hash`

**Alembic migration:**
```bash
alembic init alembic
# Write migration from models
alembic upgrade head
```

---

### 2A.3 — Step 2: Auth Router

File: `app/routers/auth.py`

- [ ] `POST /auth/google`
  - Accept Google ID token from Flutter
  - Verify with `google.oauth2.id_token.verify_oauth2_token()`
  - Upsert into `creators` table (`google_id`, `display_name`)
  - Return signed JWT: `{user_id, is_creator}`

- [ ] `POST /auth/link-wallet`
  - Require JWT in `Authorization` header
  - Accept `{wallet_address: "0x..."}`
  - Store in `creators.wallet_address`
  - Return `200 OK`

- [ ] `GET /auth/me`
  - Decode JWT → return full user profile from DB

---

### 2A.4 — Step 3: Creator Registration

File: `app/services/youtube.py`

- [ ] `get_channel_metrics(channel_id: str) → dict`
  - YouTube Data API v3: `channels.list(part="statistics", id=channel_id)`
  - Return `{subscriber_count, view_count, video_count}`

- [ ] `assign_tier(subscriber_count: int) → dict`
  - Micro (`< 50,000`): `{tier: 0, basePrice: 600_000, kScaled: 8_000_000}`
  - Mid (`50,000–500,000`): `{tier: 1, basePrice: 2_350_000, kScaled: 30_000_000}`
  - Star (`> 500,000`): `{tier: 2, basePrice: 9_400_000, kScaled: 120_000_000}`

File: `app/routers/creators.py`

- [ ] `POST /creators/register`
  - Require JWT
  - Accept `{youtube_channel_id}`
  - Call `youtube.get_channel_metrics()` → `assign_tier()`
  - Call `web3_service.deploy_creator()` → get contract address
  - Store in DB
  - Return creator profile with contract address

---

### 2A.5 — Step 4: Web3 Service + Event Listener

File: `app/services/web3_service.py`

- [ ] `deploy_creator(wallet, tier, basePrice, kScaled) → str`
  - Build + sign tx calling `factory.functions.deployCreator(...)`
  - Broadcast, wait for receipt, parse `CreatorDeployed` event, return contract address

- [ ] `get_creator_contract(address: str)` → web3 contract instance with CreatorToken ABI

- [ ] `get_buy_quote(contract_address, amount) → dict`
  - Call `contract.functions.getBuyQuote(amount).call()` — view, no gas

- [ ] `get_sell_quote(contract_address, amount) → dict`
  - Call `contract.functions.getSellQuote(amount).call()` — view, no gas

- [ ] `get_current_price(contract_address) → int`
  - Call `contract.functions.getCurrentPrice().call()`

- [ ] `get_market_status() → dict`
  - Call `factory.functions.isMarketOpen().call()`

File: `app/tasks/event_listener.py`

Run as a separate process (not a Celery task — needs persistent connection):
- [ ] Load all known creator contract addresses from DB on startup
- [ ] For each address, create event filters: `PassBought`, `PassSold`, `PriceChanged`
- [ ] Poll loop every 2 seconds: `filter.get_new_entries()`
- [ ] On each event:
  - Write to `price_events` table (`event_type`, `price_usdc`, `supply`, `tx_hash`, `block_timestamp`)
  - Push tick to WebSocket manager: `await manager.broadcast(creator_id, tick_message)`
- [ ] On new creator registration: add that contract's filters dynamically

---

### 2A.6 — Step 5: Candle Aggregation

File: `app/tasks/candle_tasks.py`

- [ ] `aggregate_5m_candles()` — Celery task, every 5 minutes
  - For each creator: query `price_events` for `block_timestamp` in last 5-minute window
  - Compute: `open` = first price, `high` = max, `low` = min, `close` = last price, `volume` = count
  - Upsert into `candles_5m` (unique on `creator_id + open_time`)
  - After upsert: push `type: "candle"` message to WebSocket manager

File: `app/routers/creators.py`

- [ ] `GET /creators/{id}/candles?tf=5m`
  - Query `candles_5m` for this creator ordered by `open_time` ASC
  - Return `[{time, open, high, low, close, volume}]`

---

### 2A.7 — Step 6: Sentiment Pipeline

File: `app/services/sentiment.py`

Load model once at app startup (not per-request):
```python
from transformers import pipeline as hf_pipeline
sentiment_pipeline = hf_pipeline(
    "sentiment-analysis",
    model="distilbert-base-uncased-finetuned-sst-2-english"
)
```

Implement `compute_modifier(comments: list[str]) → int` exactly as in `TECHNICAL.md §8`:
- [ ] Run `sentiment_pipeline(comments, truncation=True, max_length=512)`
- [ ] Compute `net = avg_positive - avg_negative`
- [ ] Map to `modifier = 1.0 + (net * 0.5)` → return `int(modifier * 10000)`

File: `app/tasks/sentiment_tasks.py`

- [ ] `fetch_youtube_comments(creator_id)` — get 100 most recent comments from YouTube API
  - Check Redis for already-processed comment IDs (`SISMEMBER`), skip them
  - Store new IDs in Redis with 24h TTL (`SADD + EXPIRE`)
  - Return only new comments

- [ ] `run_nlp_pipeline(creator_id, comments)` — calls `compute_modifier()`
  - Insert result into `sentiment_history` table

- [ ] `maybe_update_on_chain(creator_id, new_bps, current_bps)`
  - Only call oracle if `abs(new_bps - current_bps) / current_bps >= 0.05`
  - This saves gas on minor fluctuations

- [ ] `run_all_creators()` — top-level beat task: chains the above 3 for every creator in DB

File: `app/services/oracle.py`

- [ ] `update_sentiment(contract_address, new_bps)` — sign + send `updateSentimentModifier(new_bps)` tx via backend wallet
- [ ] After tx confirmed: push `type: "sentiment"` message to WebSocket manager

---

### 2A.8 — Step 7: Market Open/Close

File: `app/tasks/market_tasks.py`

- [ ] `open_market_session()`
  - Call `factory.functions.setMarketOpen(True)` via signed tx
  - For each creator contract: call `openSession()` (permissionless, but backend triggers it)
  - On failure: `self.retry(countdown=120, max_retries=5)` — retries every 2 min up to 10 min

- [ ] `close_market_session()`
  - Call `factory.functions.setMarketOpen(False)`
  - Call `closeSession()` on each creator contract via oracle wallet

File: `app/tasks/celery_app.py`

```python
CELERYBEAT_SCHEDULE = {
    'open-morning':  {'task': 'tasks.market_tasks.open_market_session',
                      'schedule': crontab(hour=4, minute=30)},    # 10:00 IST = 04:30 UTC
    'close-morning': {'task': 'tasks.market_tasks.close_market_session',
                      'schedule': crontab(hour=8, minute=30)},    # 14:00 IST = 08:30 UTC
    'open-evening':  {'task': 'tasks.market_tasks.open_market_session',
                      'schedule': crontab(hour=12, minute=30)},   # 18:00 IST = 12:30 UTC
    'close-evening': {'task': 'tasks.market_tasks.close_market_session',
                      'schedule': crontab(hour=16, minute=30)},   # 22:00 IST = 16:30 UTC
    'candles':       {'task': 'tasks.candle_tasks.aggregate_5m_candles',
                      'schedule': crontab(minute='*/5')},
    'sentiment':     {'task': 'tasks.sentiment_tasks.run_all_creators',
                      'schedule': crontab(minute='*/30')},
}
```

File: `app/routers/market.py`

- [ ] `GET /market/status` → `{isOpen, sessionStart, sessionEnd, nextOpen}`
  - Read `factory.functions.isMarketOpen().call()` — view call, no gas
  - Compute `nextOpen` from hardcoded beat schedule

- [ ] `POST /market/open` — manual admin override, no auth for demo
- [ ] `POST /market/close` — same

---

### 2A.9 — Step 8: Remaining Endpoints

File: `app/routers/creators.py`

- [ ] `GET /creators` — list all creators
  - For each: call `getCurrentPrice()` + `aiModifierBps()` view fns on their contracts
  - Return `[{id, name, tier, price, aiModifierBps, contractAddress}]`

- [ ] `GET /creators/{id}` — full detail including `currentSupply`, `sessionOpeningPrice`

- [ ] `GET /creators/{id}/quote/buy?amount=N` — proxy to `web3_service.get_buy_quote()`

- [ ] `GET /creators/{id}/quote/sell?amount=N` — proxy to `web3_service.get_sell_quote()`

- [ ] `GET /creators/{id}/sentiment` → latest row from `sentiment_history`

File: `app/routers/portfolio.py`

- [ ] `GET /portfolio/{wallet}`
  - For each creator contract: call `balanceOf(wallet, TOKEN_ID)` view fn
  - For non-zero balances: fetch current price, compute current value
  - Return `[{creatorId, name, amountHeld, currentPriceUsdc, totalValueUsdc}]`

File: `app/routers/dashboard.py`

- [ ] `GET /dashboard/earnings` → call `contract.functions.creatorFeeBalance().call()`
- [ ] `POST /dashboard/withdraw` → sign + send `creatorWithdraw()` tx via backend wallet (on behalf of creator) or return raw tx for WalletConnect signing
- [ ] `GET /dashboard/transactions` → query `price_events` filtered to this creator

---

### 2A.10 — Step 9: WebSocket

File: `app/websocket/manager.py`

```python
class ConnectionManager:
    # creator_id → list of WebSocket connections
    active_connections: dict[int, list[WebSocket]] = {}

    async def connect(ws: WebSocket, creator_id: int): ...
    async def disconnect(ws: WebSocket, creator_id: int): ...
    async def broadcast(creator_id: int, message: dict): ...
    async def broadcast_all(message: dict): ...  # for market_status events
```

File: `app/main.py`

- [ ] `WebSocket /ws/market`
  - On connect: read `{"action": "subscribe", "creator_id": N}`
  - Register with manager
  - Keep alive loop; on disconnect: unregister

Push message shapes:
```json
{"type": "tick",          "creator_id": 42, "data": {"price": 2.55, "supply": 14, "event": "buy", "timestamp": 1718000000}}
{"type": "candle",        "creator_id": 42, "data": {"time": 1718000000, "open": 2.38, "high": 2.65, "low": 2.31, "close": 2.55}}
{"type": "sentiment",     "creator_id": 42, "data": {"modifierBps": 11500, "timestamp": 1718000000}}
{"type": "market_status",                   "data": {"isOpen": true, "sessionEnd": 1718014800}}
```

---

### 2A.11 — Step 10: Demo Simulator

File: `demo_simulator.py`

```python
# 5 pre-funded wallets with Base Sepolia ETH + USDC
# Loop every 15–45 seconds (random.uniform):
#   - Pick random wallet from list
#   - Pick random creator contract (micro/mid/star)
#   - If wallet has token balance > 0: randomly buy or sell
#   - If no balance: always buy
#   - Buy: USDC approve → buyPass(random 1–3)
#   - Sell: sellPass(random 1–2, capped at balance)
#   - Print: wallet, action, amount, tx_hash, new price
```

Run this for 30+ minutes before demo to seed realistic candle history.

---

### ✅ Phase 2A Exit Criteria

- [ ] `uvicorn app.main:app --reload` starts with no errors
- [ ] All endpoints return valid JSON (verify with Postman or `httpx`)
- [ ] Celery worker + beat start: `celery -A app.tasks.celery_app worker --beat`
- [ ] Event listener daemon captures `PriceChanged` event from simulator within 10 seconds
- [ ] WebSocket client receives tick messages during simulator run
- [ ] `demo_simulator.py` runs 5 minutes without crash
- [ ] At least one 5m candle exists in `candles_5m` table after simulator run

---
---

## PHASE 2B — Flutter Frontend `[GARV]`
### ⏱ Estimated: 8–10 hours | Runs fully parallel to HAR's Phase 2A

**Prerequisites before starting:** ABI JSON from Phase 1 stored in `assets/abis/`. Contract addresses in `constants.dart`. HAR's ngrok URL (or use mock API responses initially — stub the service layer).

---

### 2B.1 — Project Setup

```bash
flutter create socialfi_app && cd socialfi_app
```

`pubspec.yaml` dependencies:
```yaml
dependencies:
  flutter_bloc: ^8.1.0
  walletconnect_flutter_v2: ^2.1.0
  webview_flutter: ^4.4.0
  http: ^1.1.0
  web_socket_channel: ^2.4.0
  google_sign_in: ^6.1.0
  cached_network_image: ^3.3.0
  fl_chart: ^0.65.0
  flutter_secure_storage: ^9.0.0
  convert: ^3.1.0
```

**Directory structure:**
```
lib/
├── main.dart
├── config/
│   └── constants.dart            # API base URL, WC project ID, ABI, contract addresses
├── models/
│   ├── creator.dart
│   ├── candle.dart
│   ├── quote.dart
│   └── portfolio_item.dart
├── services/
│   ├── api_service.dart          # REST calls
│   ├── auth_service.dart         # Google OAuth + JWT storage
│   ├── wallet_service.dart       # WalletConnect v2
│   └── websocket_service.dart    # WS connection + message routing
├── blocs/
│   ├── auth/
│   ├── market/
│   ├── creator_detail/
│   └── portfolio/
└── screens/
    ├── auth_screen.dart
    ├── wallet_link_screen.dart
    ├── home_screen.dart
    ├── creator_detail_screen.dart
    └── creator_dashboard_screen.dart
assets/
└── abis/
    ├── CreatorToken.json          # from Phase 1
    └── SocialFiFactory.json       # from Phase 1
```

---

### 2B.2 — Step 1: Auth Flow

File: `lib/services/auth_service.dart`

- [ ] `signInWithGoogle() → String idToken` — use `google_sign_in` package
- [ ] `postGoogleToken(idToken) → {jwt, userId, isCreator}` — `POST /auth/google`
- [ ] `storeJwt(jwt)` — persist in `flutter_secure_storage`
- [ ] `linkWallet(address)` — `POST /auth/link-wallet` with stored JWT in header
- [ ] `getCurrentUser() → User?` — decode stored JWT, call `GET /auth/me`

File: `lib/screens/auth_screen.dart`

- [ ] Google Sign In button
- [ ] On tap: call `auth_service.signInWithGoogle()` → `postGoogleToken()` → store JWT
- [ ] Navigate to `WalletLinkScreen`

File: `lib/screens/wallet_link_screen.dart`

- [ ] Init WalletConnect v2 `Web3App` with project ID from `constants.dart`
- [ ] "Connect Wallet" button → open WalletConnect modal → deep link to MetaMask/Trust Wallet
- [ ] On session established: extract account address
- [ ] Call `auth_service.linkWallet(address)`
- [ ] Navigate to `HomeScreen`

---

### 2B.3 — Step 2: Market Feed

File: `lib/services/api_service.dart`

- [ ] `getCreators() → List<Creator>` — `GET /creators`, attaches JWT header
- [ ] `getMarketStatus() → MarketStatus` — `GET /market/status`
- [ ] All methods read JWT from `flutter_secure_storage` and add `Authorization: Bearer <jwt>`

File: `lib/screens/home_screen.dart` — Market tab

- [ ] Creator list: `ListView` of cards showing:
  - Creator name + avatar (`cached_network_image`)
  - Current price in USDC (formatted to 4 decimals)
  - AI modifier badge — green chip if `bps > 10000`, red if `< 10000`, grey if `= 10000`
  - Tier chip: Micro / Mid / Star
- [ ] Sort `DropdownButton`: by AI modifier / by price / by tier
- [ ] Market status banner at top: `OPEN` (green) or `CLOSED` (red) + next session time
- [ ] Pull-to-refresh with `RefreshIndicator`
- [ ] Tap card → push `CreatorDetailScreen(creatorId)`

---

### 2B.4 — Step 3: Creator Detail Screen

File: `lib/screens/creator_detail_screen.dart`

**Section 1: TradingView Chart**
- [ ] On mount: `GET /creators/{id}/candles` → get historical OHLC array
- [ ] Load local HTML asset (`assets/tradingview_chart.html`) in `WebViewController`
  - HTML file uses TradingView Lightweight Charts CDN
  - Exposes `window.initChart(candleArray)` and `window.addTick(price, time)` as JS functions
- [ ] After webview loads: call `controller.runJavaScript("initChart(${jsonEncode(candles)})")`
- [ ] WebSocket subscription (from `websocket_service`) → on `type: "tick"` → call `controller.runJavaScript("addTick(...)")`

**Section 2: Stats row** (below chart)
- [ ] Current price (USDC) | Current supply | AI modifier badge | Tier label

**Section 3: Buy / Sell tabs** (`TabBar`)

Buy tab:
- [ ] `NumberStepper` for amount (1–10)
- [ ] On amount change: debounce 300ms → `GET /creators/{id}/quote/buy?amount=N`
- [ ] Display quote breakdown:
  - Token cost (USDC)
  - Platform fee (1%)
  - Gas estimate: hardcoded "< $0.01 on Base L2"
  - Total cost (bold)
- [ ] "Approve USDC" button → construct ERC-20 `approve(contractAddress, totalCost)` tx → `wallet_service.sendTransaction()`
- [ ] After approval: "Confirm Buy" button → construct `buyPass(amount)` calldata using ABI from assets → `wallet_service.sendTransaction()`
- [ ] Show pending spinner → listen on WebSocket for `PassBought` with matching buyer → show success snackbar

Sell tab (same structure):
- [ ] Uses `getSellQuote`, constructs `sellPass(amount)` calldata
- [ ] Shows expected USDC return after 1% fee

---

### 2B.5 — Step 4: Portfolio Tab

File: `lib/services/api_service.dart`

- [ ] `getPortfolio(walletAddress) → List<PortfolioItem>` — `GET /portfolio/{wallet}`

File: `lib/screens/home_screen.dart` — Portfolio tab

- [ ] Total portfolio value header (sum of all positions in USDC)
- [ ] `ListView` of held tokens: creator name, amount held, current value (USDC)
- [ ] Empty state: "You don't hold any Fan Passes yet" with CTA to Market tab
- [ ] Tap item → push `CreatorDetailScreen(creatorId)` with sell tab pre-selected (pass `initialTab: 1`)

---

### 2B.6 — Step 5: Creator Dashboard

File: `lib/screens/creator_dashboard_screen.dart`

Shown in Profile tab only if `currentUser.isCreator == true`.

- [ ] `GET /dashboard/earnings` → show withdrawable USDC balance
- [ ] `GET /dashboard/transactions` → scrollable fee history list (buyer address, amount, timestamp)
- [ ] "Withdraw" button:
  - `POST /dashboard/withdraw` — backend builds + signs the tx OR returns raw tx
  - If returning raw tx: sign via WalletConnect → broadcast
  - On confirmed: refresh balance to 0

---

### 2B.7 — Step 6: WebSocket Live Updates

File: `lib/services/websocket_service.dart`

- [ ] Connect `WebSocketChannel` to `WS_URL` from `constants.dart` on app start
- [ ] `subscribe(int creatorId)` — sends `{"action": "subscribe", "creator_id": creatorId}`
- [ ] Expose `Stream<Map>` for consumers to listen to
- [ ] Route by `type` in listeners:
  - `tick` → update creator card price in Market tab + call `addTick` on chart webview
  - `candle` → call `initChart` / append candle on chart webview
  - `sentiment` → update AI modifier badge on creator card + detail screen
  - `market_status` → update open/close banner across all screens

---

### 2B.8 — Step 7: Wallet Service

File: `lib/services/wallet_service.dart`

- [ ] `init()` — create `Web3App(projectId: WALLETCONNECT_PROJECT_ID)`
- [ ] `connectWallet() → String address` — create session, handle WC modal, extract account
- [ ] `sendTransaction({required String to, required String data, String value = "0x0"}) → String txHash`
  - Construct `eth_sendTransaction` request
  - Set `chainId: 84532` (Base Sepolia)
  - Request via WalletConnect session → deep link to wallet app → user signs
  - Return tx hash
- [ ] `encodeCalldata(String functionSig, List args) → String` — ABI-encode using `convert` package + ABI JSON from assets

**Note for GARV:** Show a "Get testnet USDC" helper link (Circle faucet URL) if `balanceOf(wallet, USDC)` is 0 when user tries to buy.

---

### ✅ Phase 2B Exit Criteria

- [ ] Google Sign In completes and JWT is stored
- [ ] WalletConnect connects to MetaMask on Base Sepolia (chain 84532)
- [ ] Market tab loads creator list with prices from API
- [ ] TradingView chart renders in WebView with historical candles
- [ ] Buy quote shows correct USDC breakdown
- [ ] "Confirm Buy" triggers WalletConnect signing prompt
- [ ] WebSocket price tick updates creator card price without page refresh

---
---

## PHASE 3 — Integration `[GARV]`
### ⏱ Estimated: 3–4 hours

Integration coordination is assigned to GARV since it requires both sides to be working but HAR's backend is the dependency. GARV drives the sequence; HAR responds to bug reports from the backend side.

**Sequence:**

1. `[HAR]` Start backend locally: `uvicorn app.main:app --reload`
2. `[HAR]` Expose via ngrok: `ngrok http 8000` → share the HTTPS + WSS URLs in chat
3. `[GARV]` Update `lib/config/constants.dart` with ngrok URLs
4. `[GARV]` Run through E2E flow, log any failures, tag as `[HAR-BUG]` or `[GARV-BUG]`:

| Step | GARV Action | HAR Confirms |
|---|---|---|
| 1 | Open Market tab | 3 demo creators visible with real prices |
| 2 | Buy 1 token (test wallet) | WalletConnect prompts → tx confirmed → WebSocket tick received |
| 3 | Watch chart | Price updates after buy without refresh |
| 4 | HAR calls `POST /market/close` | Buy attempt → revert shown in app |
| 5 | HAR triggers `updateSentimentModifier(14000)` manually | Modifier badge updates live on GARV's screen |
| 6 | HAR runs `demo_simulator.py` 5 min | Candle chart shows OHLC movement |
| 7 | GARV taps Withdraw on Dashboard | USDC transferred, balance resets |
| 8 | Force price to upper circuit bound | Revert message shown in app |

5. `[HAR]` Fix all `[HAR-BUG]` items; `[GARV]` fixes `[GARV-BUG]` items
6. `[HAR]` Deploy backend to Railway or Render — add all env vars in dashboard
7. `[GARV]` Update `constants.dart` to production URL, rebuild app
8. `[HAR]` Run `demo_simulator.py` against production for 30 minutes to seed demo data

---

## PHASE 4 — Demo Prep `[GARV]`
### ⏱ Estimated: 2 hours

GARV owns the demo prep and rehearsal. HAR is on standby to fix backend issues and run the simulator.

**GARV's pre-demo checklist:**
- [ ] 5 test wallets imported into MetaMask (GARV holds the private keys)
- [ ] Confirm each wallet has Base Sepolia ETH — faucet: `https://www.coinbase.com/faucets/base-ethereum-sepolia-faucet`
- [ ] Confirm each wallet has testnet USDC — faucet: `https://faucet.circle.com`
- [ ] Chart shows real moving candles (HAR has run simulator for 30 min)
- [ ] AI modifier badge is non-neutral on at least one creator (HAR has manually updated it)
- [ ] Record 30-second backup video: live chart moving + one buy tx completing

**HAR's pre-demo checklist:**
- [ ] `demo_simulator.py` running against production, steady state
- [ ] Backend logs clean (no repeated errors)
- [ ] YouTube API quota at < 500 units used for the day
- [ ] Testnet USDC pre-funded on all 5 simulator wallets
- [ ] Terminal open and ready for: `curl -X POST .../market/open` (manual override)

**Demo script — GARV presents, HAR runs backend commands on cue:**

1. Open Flutter app → show Market tab with 3 live creators and moving prices
2. Tap mid-tier creator → show 5m candlestick chart with real OHLC history
3. Buy 2 tokens live → WalletConnect signs → chart price jumps → supply count increments
4. Point to AI modifier badge: *"This is DistilBERT, running on our backend, analyzing this creator's YouTube comments in real time"*
5. `[HAR ON CUE]` call `updateSentimentModifier(14000)` from terminal → badge turns green on GARV's screen in real time
6. Show circuit breaker: try to force a buy at 11% above session open → tx reverts → app shows error
7. Go to Creator Dashboard → show 0.6% fees accumulated → tap Withdraw → USDC transferred

---

## Contingency Table

| Problem | Impact | Owner | Fix |
|---|---|---|---|
| Base Sepolia RPC down | Nothing works | `[HAR]` | Switch to Alchemy: `https://base-sepolia.g.alchemy.com/v2/KEY` in backend `.env` |
| USDC faucet quota exhausted | Can't demo buys | `[HAR]` | Pre-fund all simulator wallets 12h before demo |
| YouTube quota exhausted | No live sentiment | `[HAR]` | Cache 50 real comments locally, replay through NLP pipeline at demo time |
| WalletConnect deep link broken | Can't sign txs in app | `[GARV]` | Fallback: show raw tx hex, manually paste into MetaMask browser extension |
| Celery beat misses market open | Market stays closed | `[HAR]` | Call `POST /market/open` manually before demo starts |
| Testnet slow (30s+ finality) | Demo feels stuck | `[GARV]` | Show tx hash + link to Basescan immediately; tell judges "Base usually confirms in 2 seconds, testnet is slower" |

---

## What's Real vs. Faked in the Demo

| Feature | Reality |
|---|---|
| Buy/sell transactions | Real on-chain txs on Base Sepolia |
| Candlestick chart | Real OHLC aggregated from on-chain `PriceChanged` events |
| Bonding curve pricing | Real contract math — each buy changes the price for the next buyer |
| Circuit breaker | Real contract revert — not simulated |
| AI sentiment modifier | Real DistilBERT on backend — but comments from cached/replayed YouTube data |
| Multiple fans | 5 pre-funded wallets running `demo_simulator.py` |
| Fee collection | Real 1% taken on-chain; creator balance accumulates in contract storage |

---

## Environment Variables Reference

### Backend `.env` `[HAR]`
```env
DATABASE_URL=postgresql://user:pass@localhost/socialfi
REDIS_URL=redis://localhost:6379
BACKEND_WALLET_PRIVATE_KEY=0x...
FACTORY_CONTRACT_ADDRESS=0x...
USDC_CONTRACT_ADDRESS=0x036CbD53842c5426634e7929541eC2318f3dCF7e
PROTOCOL_TREASURY_ADDRESS=0x...
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
YOUTUBE_API_KEY=...
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1
```

### Flutter `lib/config/constants.dart` `[GARV]`
```dart
const String API_BASE_URL          = "https://your-backend.railway.app";
const String WS_URL                = "wss://your-backend.railway.app/ws/market";
const String WALLETCONNECT_PROJECT_ID = "...";
const int    BASE_SEPOLIA_CHAIN_ID = 84532;
const String USDC_ADDRESS          = "0x036CbD53842c5426634e7929541eC2318f3dCF7e";
// Fill in after Phase 1 deploy:
const String FACTORY_ADDRESS       = "0x...";
const String DEMO_MICRO_ADDRESS    = "0x...";
const String DEMO_MID_ADDRESS      = "0x...";
const String DEMO_STAR_ADDRESS     = "0x...";
```

---

## Quick Reference: Token Pricing at Different Supplies

### Mid-Tier Creator (basePrice = $2.35, k = 0.030)

| Supply | Price (modifier=1.0) | Price (modifier=1.5) | ≈ INR |
|--------|----------------------|----------------------|-------|
| 0 | $2.35 | $3.53 | ₹197 |
| 5 | $3.10 | $4.65 | ₹260 |
| 10 | $5.35 | $8.03 | ₹450 |
| 20 | $14.35 | $21.53 | ₹1,205 |
| 50 | $77.35 | $116.03 | ₹6,498 |

> k = 0.030 causes steep growth past ~10 tokens — early believers get the best entry price, which is the core fan incentive.
