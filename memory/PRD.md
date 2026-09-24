# Mock Crypto Exchange — Market Data Generator (PRD)

## Original Problem Statement
Build a lightweight, stateless backend that simulates a crypto exchange, emitting realistic high-frequency L2 order book depth and trade prints over WebSockets. Python + FastAPI + WebSockets, no database, fully in-memory.

## Architecture
- FastAPI app (`/app/backend/server.py`), stateless, in-memory only. No MongoDB used.
- Global `MarketSimulator` random-walks a mid-price per instrument (Gaussian shock + mild mean reversion).
- Per-connection, per-symbol asyncio `Subscription` tasks stream data with a shared send lock.
- Routes prefixed with `/api` for Kubernetes ingress. WebSocket at `/api/ws/market-data`.

## Endpoints
- `GET /api/` — health message
- `GET /api/symbols` — supported instruments + current mids + config
- `WS /api/ws/market-data` — subscribe/unsubscribe protocol:
  - `{"action":"subscribe","symbol":"BTC-USD"}`
  - `{"action":"unsubscribe","symbol":"BTC-USD"}`
  - Emits `welcome`, `subscribed`, `unsubscribed`, `orderbook`, `trade`, `error`, `info`.

## Config
- Instruments: BTC-USD, ETH-USD, SOL-USD
- Depth: 10 levels per side; spread ~0.01% of mid; emit interval randomized 50–500 ms.
- Payloads: orderbook `{bids/asks:[{price,size}]}`, trade `{price,size,side,timestamp}`.

## Implemented (2026-06)
- Full WebSocket market-data generator, verified end-to-end over external wss URL.

## Backlog (user stated will request later)
- P1: Live trading dashboard frontend (order book depth, trade tape, price chart).
- P1: RAG-based backend.
