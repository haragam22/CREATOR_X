# Frontend Contract
> **Target Audience:** Garv (Flutter Developer)
> **Purpose:** "What does Flutter need to do to make this work?" This document defines the exact payloads, transaction flows, and state handling mechanisms required.

---

## Section 1 — Base Config

Garv hardcodes nothing. Everything comes from a single config/constants file that we keep updated when contracts deploy.

- **Base URL (Dev):** `http://localhost:8000`
- **Base URL (Prod):** `https://your-railway-url.com`
- **Auth Header:** `Authorization: Bearer <jwt_token>`
- **Content-Type:** `application/json`
- **USDC Contract:** `0x036CbD53842c5426634e7929541eC2318f3dCF7e` *(Base Sepolia Testnet)*
- **Factory Contract:** `0x8a502ad779b0153da45f4862f3599adfb034a03e` *(Base Sepolia Testnet)*
- **Chain ID:** `84532`

---

## Section 2 — Auth Flow (Exact Sequence)

Do not treat auth as random endpoints. Implement this exact Flutter code sequence:

**1. User taps "Sign in with Google"**
   → Call `GoogleSignIn().signIn()`
   → Get `idToken` from `GoogleSignInAuthentication`

**2. Exchange Token**
   → `POST /auth/google` with `{ "id_token": "..." }`
   → Store returned `access_token` in `FlutterSecureStorage`
   → Store `user_id` and `is_creator` locally

**3. Wallet Linking Check**
   → Call `GET /auth/me` (requires Bearer token)
   → If `wallet_address` is `null` in the response:
      → Show `WalletLinkScreen`
      → Use WalletConnect to initiate a session and get the user's wallet address.
      → `POST /auth/link-wallet` with `{ "wallet_address": "0x..." }` (requires Bearer token)
   → If `wallet_address` is present, proceed.

**4. Final Redirect**
   → Redirect to `HomeScreen`

---

## Section 3 — Every Response Shape Flutter Parses

Create one Dart class per response shape below. These are the exact JSON outputs from the backend.

```json
// POST /auth/google
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI...",
  "user_id": 123,
  "is_creator": false
}

// POST /auth/link-wallet
{
  "status": "success",
  "wallet_address": "0x123..."
}

// GET /auth/me
{
  "user_id": 123,
  "display_name": "Garv",
  "email": "garv@example.com",
  "wallet_address": "0x123...",
  "is_creator": true,
  "creator_profile": {
    "token_contract": "0xabc...",
    "tier": 1,
    "tier_name": "Mid",
    "base_price_usdc": 2350000,
    "youtube_channel_id": "UC123...",
    "subscriber_count": 120000
  }
}

// POST /creators/register
{
  "user_id": 123,
  "display_name": "Garv",
  "email": "garv@example.com",
  "wallet_address": "0x123...",
  "is_creator": true,
  "creator_profile": {
    "token_contract": "0xabc...",
    "tier": 1,
    "tier_name": "Mid",
    "base_price_usdc": 2350000,
    "k_value": 30000000,
    "youtube_channel_id": "UC123...",
    "subscriber_count": 120000
  }
}

// GET /creators
[
  {
    "id": 3,
    "display_name": "TechWithTim",
    "tier": 1,
    "tier_name": "Mid",
    "token_contract": "0xabc...",
    "current_price_usdc": 2550000,
    "ai_modifier_bps": 11500
  }
]

// GET /creators/{id}
{
  "id": 3,
  "display_name": "TechWithTim",
  "tier": 1,
  "tier_name": "Mid",
  "token_contract": "0xabc...",
  "current_price_usdc": 2550000,
  "current_supply": 14,
  "ai_modifier_bps": 11500,
  "subscriber_count": 145000,
  "session_opening_price_usdc": 2380000,
  "circuit_upper_usdc": 2618000,
  "circuit_lower_usdc": 2142000
}

// GET /creators/{id}/candles?tf=5m&limit=200
[
  {
    "time": 1718000000,
    "open": 2380000,
    "high": 2650000,
    "low": 2310000,
    "close": 2550000,
    "volume_tokens": 12
  }
]

// GET /creators/{id}/trades?limit=50
[
  {
    "event_type": "buy",
    "amount": 2,
    "price_usdc": 2550000,
    "tx_hash": "0xdef...",
    "timestamp": 1718000000
  }
]

// GET /creators/{id}/quote/buy?amount=N
{
  "totalCost": 5151000,
  "fee": 51000,
  "pricePerToken": 2550000
}

// GET /creators/{id}/quote/sell?amount=N
{
  "totalReturn": 5049000,
  "fee": 51000,
  "pricePerToken": 2550000
}

// GET /creators/{id}/sentiment
{
  "modifierBps": 11500,
  "rawScore": 0.8500,
  "lastUpdated": 1718000000
}

// GET /market/status
{
  "isOpen": true,
  "sessionStart": 1718000000,
  "sessionEnd": 1718014800,
  "nextOpen": 1718043600
}

// GET /portfolio/{wallet}
[
  {
    "creator_id": 3,
    "display_name": "TechWithTim",
    "token_contract": "0xabc...",
    "balance": 5,
    "current_price_usdc": 2550000,
    "total_value_usdc": 12750000
  }
]

// GET /dashboard/earnings
{
  "totalAccrued": 1500000,
  "withdrawable": 500000
}

// POST /dashboard/withdraw
{
  "tx_hash": "0x789...",
  "amount_withdrawn": 500000,
  "status": "confirmed"
}
```

---

## Section 4 — WalletConnect Transaction Specs

### BUY TRANSACTION
**To:** `<creator token_contract address>`
**Function:** `buyPass(uint256 amount)`
**ABI:** `{"inputs":[{"internalType":"uint256","name":"amount","type":"uint256"}],"name":"buyPass","outputs":[],"stateMutability":"nonpayable","type":"function"}`

**Pre-condition: User must approve USDC spend first**
The `approve` tx MUST happen before `buyPass` or the contract will revert.
**USDC Approval Transaction:**
- **To:** `USDC_CONTRACT_ADDRESS`
- **Function:** `approve(address spender, uint256 amount)`
- **spender:** `<creator token_contract address>`
- **amount:** `totalCost` from `/quote/buy` (in micro-USDC, 6 decimals)

**Sequence:**
1. `GET /creators/{id}/quote/buy?amount=N` → get `totalCost`
2. Check current USDC allowance via `eth_call` to `USDC.allowance(wallet, creator_token_contract)`
3. If allowance < `totalCost`: send `approve` tx first via WalletConnect, wait for receipt/confirmation.
4. Send `buyPass(N)` tx via WalletConnect.
5. Wait for `PassBought` event or tx receipt.
6. Show success UI.

### SELL TRANSACTION
**To:** `<creator token_contract address>`
**Function:** `sellPass(uint256 amount)`
**ABI:** `{"inputs":[{"internalType":"uint256","name":"amount","type":"uint256"}],"name":"sellPass","outputs":[],"stateMutability":"nonpayable","type":"function"}`

**Sequence:**
1. `GET /creators/{id}/quote/sell?amount=N` → get `totalReturn` (for UI display)
2. Send `sellPass(N)` tx via WalletConnect. *(No USDC approval needed to sell).*
3. Wait for `PassSold` event or tx receipt.
4. Show success UI.

---

## Section 5 — WebSocket Events with Dart type annotations

Garv creates a `WebSocketService` that subscribes on screen mount.

**Connection:** `ws://host/ws/market`
**On connect:** send `{ "action": "subscribe", "creator_id": <int> }`

Messages received (parse by `"type"` field):

```json
// type: "tick"
// Update current price display, push point to chart
{ 
  "type": "tick", 
  "creator_id": 3, 
  "data": {
    "price": 2.55,        // double
    "supply": 15,         // int
    "event": "buy",       // String "buy"|"sell"
    "timestamp": 1718000  // int (unix)
  }
}

// type: "candle"
// Call chart JS: chart.update(candleData)
{ 
  "type": "candle", 
  "creator_id": 3, 
  "data": {
    "time": 1718000,      // int (unix, candle open time)
    "open": 2.38,         // double
    "high": 2.65,         // double
    "low": 2.31,          // double
    "close": 2.55         // double
  }
}

// type: "market_status"
// Update market banner, enable/disable buy-sell buttons
{ 
  "type": "market_status", 
  "data": {
    "isOpen": true,       // bool
    "sessionEnd": 1718014800  // int (unix)
  }
}

// type: "sentiment"
// Update AI modifier badge color and value
{ 
  "type": "sentiment", 
  "creator_id": 3, 
  "data": {
    "modifierBps": 11500,  // int
    "timestamp": 1718000   // int
  }
}
```

---

## Section 6 — Error Handling

Garv writes one global interceptor on his HTTP client that catches this shape and shows the right UI state.

```json
// All errors follow this shape
{
  "error_code": "MARKET_CLOSED",
  "message": "Trading is currently closed. Next session opens at 18:00 IST",
  "http_status": 503
}
```

---

## Section 7 — Shared Constants File

Garv will maintain this file in the Flutter codebase and never hardcode these inline. Both teams will coordinate to update this when contract addresses change.

```dart
class AppConstants {
  static const String baseUrl = "http://localhost:8000"; // Swap to prod
  static const int chainId = 84532;
  static const String usdcAddress = "0x036CbD53842c5426634e7929541eC2318f3dCF7e";
  static const String factoryAddress = "0x8a502ad779b0153da45f4862f3599adfb034a03e";
  static const int usdcDecimals = 6;
  
  // Tier names for UI
  static const Map<int, String> tierNames = {0: "Micro", 1: "Mid", 2: "Star"};
  static const Map<int, String> tierColors = {0: "#6B7280", 1: "#3B82F6", 2: "#F59E0B"};
}
```
