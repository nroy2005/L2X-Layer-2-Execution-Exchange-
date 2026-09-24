# Mock Crypto Exchange — Market Data Simulator & Trading Terminal

A stateless FastAPI service that simulates a cryptocurrency exchange (L2 order book, trade prints,
OHLC candles, volatility modes, spikes) over WebSockets, plus a dark-mode institutional trading
terminal built in React that consumes the feed in real time.

```
backend/   FastAPI + WebSockets, in-memory only (no database)
frontend/  React 19 + Tailwind + shadcn/ui + Lightweight Charts
```

## Run locally

Backend
```bash
cd backend
cp .env.example .env
pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 8001 --reload
```

Frontend
```bash
cd frontend
cp .env.example .env          # REACT_APP_BACKEND_URL=http://localhost:8001
yarn install
yarn start                    # http://localhost:3000
```

## Backend API

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/symbols` | Instruments, current mids, volatility modes, candle intervals |
| POST | `/api/symbols` | `{symbol, start_price?}` — list a new market (start price generated if omitted) |
| POST | `/api/symbols/{symbol}/volatility` | `{mode: calm \| normal \| volatile}` |
| POST | `/api/symbols/{symbol}/spike` | `{direction: up \| down, magnitude_pct, persist}` |
| GET | `/api/candles/{symbol}?interval=1s&limit=100` | Candle history (`1s`, `5s`, `15s`, `1m`) |
| WS | `/api/ws/market-data` | Streaming feed (see below) |

### WebSocket protocol

```jsonc
{"action": "subscribe", "symbol": "BTC-USD",
 "channels": ["orderbook", "trade", "candle"], "candle_intervals": ["1s", "5s"]}
{"action": "unsubscribe", "symbol": "BTC-USD"}
{"action": "set_volatility", "symbol": "BTC-USD", "mode": "volatile"}
{"action": "spike", "symbol": "BTC-USD", "direction": "down", "magnitude_pct": 3, "persist": false}
```

Server messages: `welcome`, `subscribed`, `unsubscribed`, `orderbook` (10 levels/side),
`trade`, `candle` (`closed: true` when the bucket rolls), `market_event`
(`volatility_changed`, `spike`), `info`, `error`. Ticks arrive every 50–500 ms per symbol.
Subscribing to an unknown but valid symbol (`ABC-USD`) creates it on the fly.

## Frontend

Single-page terminal: market selector + live mid, candlestick chart (1s/5s), split order book with
depth bars, trade tape, and a Stress Test drawer (volatility toggle, spike up/down, add market).
A single reconnecting WebSocket (`src/lib/marketFeed.js`) buffers ticks and flushes to React once
per animation frame via `useSyncExternalStore`.

## Tests

```bash
cd backend && REACT_APP_BACKEND_URL=http://localhost:8001 pytest tests/
```
