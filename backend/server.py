"""
Mock Cryptocurrency Exchange - Market Data Generator.

A lightweight, stateless FastAPI service that emits realistic high-frequency
L2 order book depth and trade prints over WebSockets. No database is used;
all market state lives in memory.
"""
import asyncio
import logging
import os
import random
import time
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI, WebSocket, WebSocketDisconnect
from starlette.middleware.cors import CORSMiddleware

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("market-data")

# ---------------------------------------------------------------------------
# Market configuration
# ---------------------------------------------------------------------------
# Each supported instrument with a starting mid-price, per-step volatility and
# the number of decimals used for price rounding.
INSTRUMENTS: Dict[str, dict] = {
    "BTC-USD": {"start": 65000.0, "vol": 0.0006, "price_dp": 2, "size_dp": 5, "base_size": 2.5},
    "ETH-USD": {"start": 3500.0, "vol": 0.0008, "price_dp": 2, "size_dp": 4, "base_size": 25.0},
    "SOL-USD": {"start": 150.0, "vol": 0.0012, "price_dp": 3, "size_dp": 2, "base_size": 400.0},
}

DEPTH_LEVELS = 10          # price levels per side of the book
SPREAD_PCT = 0.0001        # ~0.01% of mid -> tight, liquid market
MIN_INTERVAL_MS = 50
MAX_INTERVAL_MS = 500


class MarketSimulator:
    """Holds a continuously random-walking mid-price for every instrument.

    A single global walker keeps all connected clients consistent with each
    other while remaining entirely in-memory and stateless across restarts.
    """

    def __init__(self):
        self.mids: Dict[str, float] = {sym: cfg["start"] for sym, cfg in INSTRUMENTS.items()}

    def step(self, symbol: str) -> float:
        """Advance the mid-price for `symbol` by one random-walk step."""
        cfg = INSTRUMENTS[symbol]
        mid = self.mids[symbol]
        # Gaussian pct return with a tiny mean-reversion pull toward the start.
        shock = random.gauss(0.0, 1.0) * cfg["vol"]
        reversion = (cfg["start"] - mid) / cfg["start"] * 0.02
        mid = mid * (1.0 + shock + reversion)
        self.mids[symbol] = mid
        return mid


simulator = MarketSimulator()


def _now_ms() -> int:
    return int(time.time() * 1000)


def build_order_book(symbol: str, mid: float) -> dict:
    """Construct an L2 order book snapshot with `DEPTH_LEVELS` per side."""
    cfg = INSTRUMENTS[symbol]
    pdp, sdp = cfg["price_dp"], cfg["size_dp"]
    spread = mid * SPREAD_PCT
    best_bid = mid - spread / 2.0
    best_ask = mid + spread / 2.0
    tick = spread  # level-to-level increment

    bids, asks = [], []
    for i in range(DEPTH_LEVELS):
        bid_price = best_bid - i * tick
        ask_price = best_ask + i * tick
        # Liquidity generally thickens away from the touch.
        depth_factor = 1.0 + i * random.uniform(0.1, 0.4)
        bids.append({
            "price": round(bid_price, pdp),
            "size": round(cfg["base_size"] * random.uniform(0.05, 0.6) * depth_factor, sdp),
        })
        asks.append({
            "price": round(ask_price, pdp),
            "size": round(cfg["base_size"] * random.uniform(0.05, 0.6) * depth_factor, sdp),
        })

    return {
        "type": "orderbook",
        "symbol": symbol,
        "timestamp": _now_ms(),
        "bids": bids,
        "asks": asks,
    }


def build_trade(symbol: str, mid: float) -> dict:
    """Construct a single executed trade print around the current mid."""
    cfg = INSTRUMENTS[symbol]
    pdp, sdp = cfg["price_dp"], cfg["size_dp"]
    spread = mid * SPREAD_PCT
    side = random.choice(["buy", "sell"])
    # Buys lift the ask, sells hit the bid, with occasional price improvement.
    if side == "buy":
        price = mid + spread / 2.0 * random.uniform(0.2, 1.0)
    else:
        price = mid - spread / 2.0 * random.uniform(0.2, 1.0)

    return {
        "type": "trade",
        "symbol": symbol,
        "timestamp": _now_ms(),
        "price": round(price, pdp),
        "size": round(cfg["base_size"] * random.uniform(0.005, 0.15), sdp),
        "side": side,
    }


class Subscription:
    """Streams market data for one symbol to one websocket connection."""

    def __init__(self, websocket: WebSocket, symbol: str, send_lock: asyncio.Lock):
        self.websocket = websocket
        self.symbol = symbol
        self.send_lock = send_lock
        self.task: asyncio.Task | None = None

    def start(self):
        self.task = asyncio.create_task(self._run())

    async def stop(self):
        if self.task:
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task

    async def _send(self, payload: dict):
        async with self.send_lock:
            await self.websocket.send_json(payload)

    async def _run(self):
        try:
            while True:
                mid = simulator.step(self.symbol)
                await self._send(build_order_book(self.symbol, mid))
                # Not every tick has a trade; emit with high probability.
                if random.random() < 0.8:
                    await self._send(build_trade(self.symbol, mid))
                delay = random.randint(MIN_INTERVAL_MS, MAX_INTERVAL_MS) / 1000.0
                await asyncio.sleep(delay)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # connection dropped mid-send, etc.
            logger.info("Stream for %s ended: %s", self.symbol, exc)


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="Mock Crypto Exchange - Market Data")
api_router = APIRouter(prefix="/api")


@api_router.get("/")
async def root():
    return {"message": "Mock Crypto Exchange market-data service is running"}


@api_router.get("/symbols")
async def symbols():
    """List supported instruments and their current mid-prices."""
    return {
        "symbols": [
            {"symbol": sym, "mid": round(simulator.mids[sym], INSTRUMENTS[sym]["price_dp"])}
            for sym in INSTRUMENTS
        ],
        "depth_levels": DEPTH_LEVELS,
        "spread_pct": SPREAD_PCT,
        "interval_ms": [MIN_INTERVAL_MS, MAX_INTERVAL_MS],
    }


app.include_router(api_router)


@app.websocket("/api/ws/market-data")
async def market_data_ws(websocket: WebSocket):
    """Client protocol (JSON messages):

        {"action": "subscribe",   "symbol": "BTC-USD"}
        {"action": "unsubscribe", "symbol": "BTC-USD"}

    On subscribe the server streams `orderbook` and `trade` payloads for the
    requested symbol until unsubscribed or the socket closes.
    """
    await websocket.accept()
    send_lock = asyncio.Lock()
    subscriptions: Dict[str, Subscription] = {}

    await websocket.send_json({
        "type": "welcome",
        "message": "Connected to Mock Crypto Exchange market-data feed.",
        "available_symbols": list(INSTRUMENTS.keys()),
        "timestamp": _now_ms(),
    })

    try:
        while True:
            msg = await websocket.receive_json()
            action = (msg.get("action") or msg.get("type") or "").lower()
            symbol = (msg.get("symbol") or "").upper()

            if action == "subscribe":
                if symbol not in INSTRUMENTS:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Unknown symbol '{symbol}'.",
                        "available_symbols": list(INSTRUMENTS.keys()),
                    })
                    continue
                if symbol in subscriptions:
                    await websocket.send_json({
                        "type": "info",
                        "message": f"Already subscribed to {symbol}.",
                    })
                    continue
                sub = Subscription(websocket, symbol, send_lock)
                subscriptions[symbol] = sub
                sub.start()
                await websocket.send_json({
                    "type": "subscribed",
                    "symbol": symbol,
                    "timestamp": _now_ms(),
                })

            elif action == "unsubscribe":
                sub = subscriptions.pop(symbol, None)
                if sub:
                    await sub.stop()
                await websocket.send_json({
                    "type": "unsubscribed",
                    "symbol": symbol,
                    "timestamp": _now_ms(),
                })

            else:
                await websocket.send_json({
                    "type": "error",
                    "message": "Unknown action. Use 'subscribe' or 'unsubscribe'.",
                })

    except WebSocketDisconnect:
        logger.info("Client disconnected.")
    finally:
        for sub in subscriptions.values():
            await sub.stop()


app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)
