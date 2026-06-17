# SocialFi Backend API Specification

This document details all the required endpoints for the full FastAPI backend, extracted from `TECHNICAL.md` and `IMPLEMENTATION.md`. We will review these endpoints, iterate on them if necessary, and use this as a reference before building Phase 2A.2.

> [!IMPORTANT]
> Please review this specification. Let me know if any endpoints are missing, if parameters need to be added, or if we should iterate on the payload structures before we jump into database setup and routing!

---

## 1. Auth Endpoints (`/auth`)
These endpoints handle Google OAuth and wallet linking.

| Method | Endpoint | Description | Request Body | Response Payload |
|--------|----------|-------------|--------------|------------------|
| `POST` | `/auth/google` | Exchange Google token for a JWT | `{ "id_token": "..." }` | `{ "access_token": "...", "user_id": 123, "is_creator": bool }` |
| `POST` | `/auth/link-wallet` | Bind a Web3 wallet address to the user | `{ "wallet_address": "0x..." }` | HTTP 200 OK |
| `GET`  | `/auth/me` | Fetch full profile data | (Requires Auth) | Profile dictionary |

---

## 2. Creator Endpoints (`/creators`)
Manage creator registration, fetching creator data, and token price/quotes.

| Method | Endpoint | Description | Request | Response |
|--------|----------|-------------|---------|----------|
| `POST` | `/creators/register` | Register creator, evaluates YouTube metrics, assigns tier, deploys token contract | `{ "youtube_channel_id": "..." }` | Complete Creator Profile + `token_contract` address |
| `GET`  | `/creators` | List all available creators with their current price and AI modifier | None | Array of Creator profiles |
| `GET`  | `/creators/{id}` | Detailed info for a specific creator including supply and price | None | Creator detail payload |
| `GET`  | `/creators/{id}/candles` | Get OHLC candlestick data. Supports query `?tf=5m` | None | `[{time, open, high, low, close}, ...]` |
| `GET`  | `/creators/{id}/quote/buy` | Fetch total cost including fee to buy `N` tokens. Uses `?amount=N` | None | `{ "totalCost": ..., "fee": ..., "pricePerToken": ... }` |
| `GET`  | `/creators/{id}/quote/sell`| Fetch return amount after fee to sell `N` tokens. Uses `?amount=N` | None | `{ "totalReturn": ..., "fee": ..., "pricePerToken": ... }` |
| `GET`  | `/creators/{id}/sentiment` | Fetch the current AI sentiment modifier and raw score | None | `{ "modifierBps": ..., "rawScore": ..., "lastUpdated": ... }` |

---

## 3. Market Endpoints (`/market`)
Handle the overall trading market session states.

| Method | Endpoint | Description | Request | Response |
|--------|----------|-------------|---------|----------|
| `GET`  | `/market/status` | Read current market timing/status | None | `{ "isOpen": bool, "sessionStart": ..., "sessionEnd": ..., "nextOpen": ... }` |
| `POST` | `/market/open` | Internal/Cron endpoint to trigger `openSession()` across active token contracts | Internal Auth | `{ "status": "success" }` |
| `POST` | `/market/close` | Internal/Cron endpoint to handle closing the market session | Internal Auth | `{ "status": "success" }` |

---

## 4. Portfolio Endpoints (`/portfolio`)
View holdings.

| Method | Endpoint | Description | Request | Response |
|--------|----------|-------------|---------|----------|
| `GET`  | `/portfolio/{wallet}` | Fetch all creator tokens currently held by this wallet and their latest values | None | Array of holding balances and USD values |

---

## 5. Dashboard Endpoints (`/dashboard`)
Endpoints specifically for creators to manage their earnings. (Authenticated)

| Method | Endpoint | Description | Request | Response |
|--------|----------|-------------|---------|----------|
| `GET`  | `/dashboard/earnings` | Check accrued protocol fees allocated to the creator | None | `{ "totalAccrued": ..., "withdrawable": ... }` |
| `POST` | `/dashboard/withdraw` | Execute on-chain `creatorWithdraw()` via backend web3 service | None | Transaction details / receipt |
| `GET`  | `/dashboard/transactions` | Feed of fee-generating events for the creator | None | Array of transaction details |

---

## WebSocket Feed
**URL**: `ws://<host>/ws/market`
**Payload to Subscribe**: `{ "action": "subscribe", "creator_id": 42 }`
Pushes asynchronous updates:
- **`candle`**: Emitted every 5 minutes when a new OHLC frame is generated.
- **`tick`**: Live price tick on every single `buy`/`sell` event.
- **`sentiment`**: When AI recalculates and updates the modifier.
- **`market_status`**: When the market transitions between open and closed.
