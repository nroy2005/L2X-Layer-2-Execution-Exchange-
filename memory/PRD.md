# Mock Crypto Exchange — Market Data Generator (PRD)

## Original Problem Statement
Build a lightweight, stateless backend that simulates a crypto exchange, emitting realistic high-frequency L2 order book depth and trade prints over WebSockets. Python + FastAPI + WebSockets, no database, fully in-memory. Frontend dashboard and RAG backend to be requested later by the user.

## Architecture
- FastAPI app (`/app/backend/server.py`), stateless, in-memory only. No MongoDB used.
- Global `MarketSimulator`: per-symbol random-walk mid (Gaussian shock × volatility-mode multiplier + mean reversion to anchor + decaying spike impulse).
- Global `CandleBook`: aggregates every trade print into OHLC candles for 1s/5s/15s/1m; keeps 500 closed candles per (symbol, interval) in memory.
- Per-connection, per-symbol asyncio `Subscription` tasks stream data with a shared send lock; global `subscribers` registry enables `market_event` broadcasts.
- Routes prefixed with `/api` for Kubernetes ingress. WebSocket at `/api/ws/market-data`.

## Endpoints
- `GET /api/` — health message
- `GET /api/symbols` — instruments (symbol, mid, start, volatility, price_dp, size_dp, dynamic) + config (volatility_modes, candle_intervals, channels)
- `POST /api/symbols` `{symbol, start_price?}` — create instrument (201 / 409 / 400). Start price generated deterministically from symbol name if omitted.
- `POST /api/symbols/{symbol}/volatility` `{mode: calm|normal|volatile}`
- `POST /api/symbols/{symbol}/spike` `{direction: up|down, magnitude_pct (0-50], persist}` — news spike / flash move; `persist` re-anchors the mean-reversion target.
- `GET /api/candles/{symbol}?interval=1s&limit=100` — closed history + live candle
- `WS /api/ws/market-data`:
  - `{"action":"subscribe","symbol":"BTC-USD","channels":["orderbook","trade","candle"],"candle_intervals":["1s","1m"],"start_price":12.5}` — unknown valid symbol (`ABC-USD` format) is auto-created (`created:true`)
  - `{"action":"unsubscribe","symbol":...}`, `{"action":"set_volatility","symbol":...,"mode":...}`, `{"action":"spike","symbol":...,"direction":...,"magnitude_pct":...}`
  - Emits `welcome`, `subscribed`, `unsubscribed`, `orderbook` (includes `volatility`), `trade`, `candle` (`closed` flag), `market_event` (`volatility_changed`, `spike`), `error`, `info`.

## Config
- Default instruments: BTC, ETH, SOL, XRP, DOGE, ADA, AVAX, LINK (all -USD)
- Depth: 10 levels/side; spread ~0.01% of mid (×0.8 calm, ×3 volatile, widened further during spikes); emit interval 50–500 ms.
- Volatility multipliers: calm 0.3×, normal 1×, volatile 4×.

## Implemented
- 2026-06: WebSocket market-data generator (orderbook + trades), verified over external wss URL.
- 2026-06: Candle feed (OHLC streaming + REST history), extra markets + dynamic symbols, volatility modes + spikes. Testing agent: 21/21 backend tests passed (`/app/backend/tests/test_market_data.py`, `/app/test_reports/iteration_1.json`).

## Backlog (user stated will request later)
- P1: Live trading dashboard frontend (order book depth, trade tape, candlestick chart, volatility controls).
- P1: RAG-based backend.
