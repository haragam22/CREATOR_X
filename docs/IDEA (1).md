# SocialFi Creator Token & Fan Pass Marketplace
## IDEA.md — Vision, Product & Token Economics

---

## 1. Problem Statement

Traditional social platforms trap creator value inside centralized systems. A YouTuber with 2M subscribers generates enormous audience loyalty — but that loyalty is unquantifiable, untradeable, and inaccessible to fans as an asset. Flat subscriptions ($5/month) give fans zero upside participation. NFT drops are illiquid one-off events with no relationship to ongoing creator performance.

**Core insight:** Creator engagement is an asset class. It should trade like one.

---

## 2. What We're Building

A decentralized mobile marketplace where every content creator has a single **Fan Pass token** — a semi-fungible ERC-1155 asset whose price is determined by an on-chain bonding curve continuously modulated by an off-chain AI sentiment engine.

Fans buy into a creator's trajectory early and profit if that creator's engagement grows. Creators earn fees from every transaction. Prices are deterministic, transparent, and manipulation-resistant via circuit breakers modeled on real stock market mechanics.

---

## 3. Core Features

### 3.1 Fan Pass Token
- One ERC-1155 token type per creator, deployed by a Factory smart contract
- Infinite liquidity — the contract is always the buyer and seller
- No order book, no counterparty needed
- Price determined by bonding curve + AI modifier (see Section 5)

### 3.2 Bonding Curve Pricing (Automated Vending Machine)
- Buying: User sends USDC → contract mints new token to user's wallet
- Selling: User returns token → contract burns it and releases USDC back
- Price increases as supply grows, decreases as supply shrinks
- No pre-minted supply, no ICO, no presale

### 3.3 AI Sentiment Modifier
- Backend continuously analyzes YouTube comments via NLP (DistilBERT)
- Derives an `AI_Modifier` scalar (range: 0.5 → 1.5)
- Positive creator momentum pushes prices up before raw subscriber numbers reflect it
- Modifier is written on-chain by the backend Oracle wallet

### 3.4 Market Hours & Circuit Breakers
- **Two daily trading sessions (IST):** 10:00 AM – 2:00 PM and 6:00 PM – 10:00 PM
- **Global market open/close flag** controlled by Celery beat scheduler
- **Per-creator circuit breaker:** ±10% daily bound from session opening price
- Any transaction breaching the bound is reverted by the contract
- This prevents hyper-speculation and manipulation during low-liquidity periods

### 3.5 Fee Structure
- **Total fee: 1% per transaction** (transparent to user in UI before confirmation)
- 0.6% → Creator's withdrawable internal balance in contract
- 0.4% → Protocol treasury multi-sig wallet
- Separate from gas fees (Base L2 gas is sub-cent)
- Creators can withdraw accumulated balance anytime via dashboard

### 3.6 Candlestick Charts
- Real OHLC candles built from on-chain `PriceChanged` events
- 5-minute timeframe
- Live streaming via WebSocket
- Rendered in Flutter using TradingView Lightweight Charts (webview)

---

## 4. Creator Tiers

Assigned at registration based on YouTube channel metrics (subscribers, 90-day avg views, upload velocity):

| Tier | Subscriber Range | BasePrice | k Value | ~Price at Token #1 | ~Price at Token #10 |
|------|-----------------|-----------|---------|---------------------|----------------------|
| Micro | < 50,000 | $0.60 USDC | 0.008 | ~$0.61 | ~$1.40 |
| Mid | 50,000 – 500,000 | $2.35 USDC | 0.030 | ~$2.38 | ~$5.35 |
| Star | > 500,000 | $9.40 USDC | 0.120 | ~$9.52 | ~$21.40 |

Mid-tier token #1 ≈ ₹200 at ₹84/$ exchange rate — the target accessible price point for Indian fans.

---

## 5. Pricing Formula

```
Price = (k × Supply² + BasePrice) × AI_Modifier
```

- `k` — tier-specific acceleration constant (controls curve steepness)
- `Supply` — current circulating supply of that creator's token
- `BasePrice` — fixed at creator registration, based on channel tier
- `AI_Modifier` — float 0.5–1.5, updated by backend Oracle, stored on-chain

---

## 6. User Journeys

### Creator
1. Sign in with Google/YouTube OAuth
2. Backend evaluates channel metrics → assigns tier → computes BasePrice
3. Factory contract deploys creator's ERC-1155 token profile
4. Creator gets a dashboard: live price chart, transaction history, accumulated fee balance
5. Creator withdraws USDC earnings anytime

### Fan/Buyer
1. Browse creator marketplace sorted by AI sentiment score or price momentum
2. Select creator → view 5m candlestick chart, current price, supply
3. Tap "Buy" → see price breakdown (token cost + 1% fee + gas estimate) before confirming
4. WalletConnect deep-links to MetaMask/Trust Wallet for signing
5. Token minted directly to fan's wallet address
6. Fan can sell anytime during market hours → USDC returned instantly

---

## 7. Why This Is Interesting

- **Infinite liquidity by design** — no stuck positions, no illiquidity traps
- **AI-price coupling** — sentiment moves prices before metrics do, rewarding early believers
- **Real market mechanics** — circuit breakers and trading sessions make it feel like a real financial instrument, not a novelty NFT
- **One contract, infinite creators** — Factory pattern scales without redeployment
- **Accessible price point** — ₹200 entry for mid-tier makes it viable for Indian users
