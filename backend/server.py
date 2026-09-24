"""
Mock Cryptocurrency Exchange - Market Data Generator.

A lightweight, stateless FastAPI service that emits realistic high-frequency
L2 order book depth, trade prints and OHLC candles over WebSockets. No
database is used; all market state lives in memory.
"""
import asyncio
import logging
import os
import random
import re
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Dict, List, Literal, Optional, Set, Tuple

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, ValidationError
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
INSTRUMENTS: Dict[str, dict] = {
    "BTC-USD": {"start": 65000.0, "vol": 0.0006, "price_dp": 2, "size_dp": 5, "base_size": 2.5},
    "ETH-USD": {"start": 3500.0, "vol": 0.0008, "price_dp": 2, "size_dp": 4, "base_size": 25.0},
    "SOL-USD": {"start": 150.0, "vol": 0.0012, "price_dp": 3, "size_dp": 2, "base_size": 400.0},
    "XRP-USD": {"start": 0.62, "vol": 0.0015, "price_dp": 4, "size_dp": 0, "base_size": 120000.0},
    "DOGE-USD": {"start": 0.145, "vol": 0.0020, "price_dp": 5, "size_dp": 0, "base_size": 500000.0},
    "ADA-USD": {"start": 0.48, "vol": 0.0015, "price_dp": 4, "size_dp": 0, "base_size": 150000.0},
    "AVAX-USD": {"start": 36.0, "vol": 0.0014, "price_dp": 3, "size_dp": 1, "base_size": 1500.0},
    "LINK-USD": {"start": 15.5, "vol": 0.0013, "price_dp": 3, "size_dp": 1, "base_size": 4000.0},
}

DEPTH_LEVELS = 10          # price levels per side of the book
SPREAD_PCT = 0.0001        # ~0.01% of mid -> tight, liquid market
MIN_INTERVAL_MS = 50
MAX_INTERVAL_MS = 500

SYMBOL_RE = re.compile(r"^[A-Z0-9]{2,10}-[A-Z]{3,5}$")

# Volatility modes: (random-walk multiplier, spread multiplier)
VOLATILITY_MODES: Dict[str, Tuple[float, float]] = {
    "calm": (0.3, 0.8),
    "normal": (1.0, 1.0),
    "volatile": (4.0, 3.0),
}

CANDLE_INTERVALS: Dict[str, int] = {"1s": 1_000, "5s": 5_000, "15s": 15_000, "1m": 60_000}
DEFAULT_CANDLE_INTERVAL = "1s"
CANDLE_HISTORY = 500
CHANNELS = {"orderbook", "trade", "candle"}

CLOCK_INTERVAL_S = 0.25       # global market clock tick (drives idle markets + mid history)
MID_HISTORY_MS = 130_000      # keep a little over 2 minutes of mids for 1m change
TICKER_INTERVAL_S = 1.0

SCENARIO_PRESETS: Dict[str, dict] = {
    "news_day": {
        "name": "News Day",
        "description": "Quiet open, headline hits, whipsaw, then a grind higher.",
        "steps": [
            {"delay_ms": 0, "action": "set_volatility", "mode": "calm"},
            {"delay_ms": 5000, "action": "set_volatility", "mode": "volatile"},
            {"delay_ms": 1000, "action": "spike", "direction": "up", "magnitude_pct": 3, "persist": True},
            {"delay_ms": 4000, "action": "spike", "direction": "down", "magnitude_pct": 1.5, "persist": False},
            {"delay_ms": 6000, "action": "spike", "direction": "up", "magnitude_pct": 2, "persist": True},
            {"delay_ms": 8000, "action": "set_volatility", "mode": "normal"},
        ],
    },
    "flash_crash": {
        "name": "Flash Crash",
        "description": "Sudden liquidation cascade followed by a violent recovery.",
        "steps": [
            {"delay_ms": 0, "action": "set_volatility", "mode": "normal"},
            {"delay_ms": 3000, "action": "spike", "direction": "down", "magnitude_pct": 8, "persist": False},
            {"delay_ms": 500, "action": "set_volatility", "mode": "volatile"},
            {"delay_ms": 5000, "action": "spike", "direction": "up", "magnitude_pct": 4, "persist": False},
            {"delay_ms": 6000, "action": "set_volatility", "mode": "normal"},
        ],
    },
    "pump_and_dump": {
        "name": "Pump & Dump",
        "description": "Staged pumps followed by a full unwind.",
        "steps": [
            {"delay_ms": 0, "action": "spike", "direction": "up", "magnitude_pct": 2, "persist": True},
            {"delay_ms": 4000, "action": "spike", "direction": "up", "magnitude_pct": 3, "persist": True},
            {"delay_ms": 4000, "action": "set_volatility", "mode": "volatile"},
            {"delay_ms": 3000, "action": "spike", "direction": "down", "magnitude_pct": 6, "persist": True},
            {"delay_ms": 5000, "action": "set_volatility", "mode": "calm"},
        ],
    },
    "calm_drift": {
        "name": "Calm Drift",
        "description": "Low-volatility weekend tape.",
        "steps": [
            {"delay_ms": 0, "action": "set_volatility", "mode": "calm"},
            {"delay_ms": 15000, "action": "set_volatility", "mode": "normal"},
        ],
    },
}


def _now_ms() -> int:
    return int(time.time() * 1000)


def _price_dp(price: float) -> int:
    if price >= 100:
        return 2
    if price >= 1:
        return 3
    if price >= 0.01:
        return 5
    return 7


def register_instrument(symbol: str, start: Optional[float] = None) -> dict:
    """Create an instrument on the fly; the start price is generated if omitted."""
    if start is None:
        rng = random.Random(symbol)  # deterministic per symbol name
        start = 10 ** rng.uniform(-2, 4)
    pdp = _price_dp(start)
    cfg = {
        "start": round(start, pdp),
        "vol": random.uniform(0.0008, 0.0018),
        "price_dp": pdp,
        "size_dp": max(0, 5 - pdp),
        "base_size": round(150_000.0 / start, max(0, 5 - pdp)),
        "dynamic": True,
    }
    INSTRUMENTS[symbol] = cfg
    simulator.add(symbol)
    logger.info("Registered instrument %s @ %s", symbol, cfg["start"])
    return cfg


class MarketSimulator:
    """Holds a continuously random-walking mid-price for every instrument."""

    def __init__(self):
        self.mids: Dict[str, float] = {}
        self.anchors: Dict[str, float] = {}
        self.modes: Dict[str, str] = {}
        self.impulses: Dict[str, float] = {}
        self.history: Dict[str, deque] = {}
        for sym in INSTRUMENTS:
            self.add(sym)

    def add(self, symbol: str):
        self.mids[symbol] = INSTRUMENTS[symbol]["start"]
        self.anchors[symbol] = INSTRUMENTS[symbol]["start"]
        self.modes[symbol] = "normal"
        self.impulses[symbol] = 0.0
        self.history[symbol] = deque(maxlen=int(MID_HISTORY_MS / 1000 / CLOCK_INTERVAL_S))

    def record(self, symbol: str):
        self.history[symbol].append((_now_ms(), self.mids[symbol]))

    def change_1m_pct(self, symbol: str) -> float:
        hist = self.history[symbol]
        if not hist:
            return 0.0
        cutoff = _now_ms() - 60_000
        base = next((mid for ts, mid in hist if ts >= cutoff), hist[0][1])
        return (self.mids[symbol] / base - 1.0) * 100.0

    def set_mode(self, symbol: str, mode: str):
        self.modes[symbol] = mode

    def spike(self, symbol: str, magnitude_pct: float, persist: bool):
        """Queue a fast directional move; positive = up, negative = down."""
        self.impulses[symbol] += magnitude_pct / 100.0
        if persist:
            self.anchors[symbol] *= 1.0 + magnitude_pct / 100.0

    def spread_mult(self, symbol: str) -> float:
        base = VOLATILITY_MODES[self.modes[symbol]][1]
        return base * (1.0 + min(abs(self.impulses[symbol]) * 40.0, 4.0))

    def step(self, symbol: str) -> float:
        cfg = INSTRUMENTS[symbol]
        mid = self.mids[symbol]
        vol_mult = VOLATILITY_MODES[self.modes[symbol]][0]
        shock = random.gauss(0.0, 1.0) * cfg["vol"] * vol_mult
        anchor = self.anchors[symbol]
        reversion = (anchor - mid) / anchor * 0.02
        # Apply ~35% of any pending spike impulse per tick so it lands in a few ticks.
        impulse = self.impulses[symbol] * 0.35
        self.impulses[symbol] -= impulse
        if abs(self.impulses[symbol]) < 1e-5:
            self.impulses[symbol] = 0.0
        mid = mid * (1.0 + shock + reversion + impulse)
        self.mids[symbol] = mid
        return mid


simulator = MarketSimulator()


class CandleBook:
    """Aggregates trade prints into OHLC candles for every supported interval."""

    def __init__(self):
        self.live: Dict[Tuple[str, str], dict] = {}
        self.history: Dict[Tuple[str, str], deque] = defaultdict(lambda: deque(maxlen=CANDLE_HISTORY))

    def on_trade(self, trade: dict) -> List[dict]:
        """Update candles with a trade; returns live updates and any closed candles."""
        out: List[dict] = []
        sym, ts, price, size = trade["symbol"], trade["timestamp"], trade["price"], trade["size"]
        sdp = INSTRUMENTS[sym]["size_dp"]
        for name, ms in CANDLE_INTERVALS.items():
            key = (sym, name)
            open_time = ts - ts % ms
            candle = self.live.get(key)
            if candle and candle["open_time"] != open_time:
                candle["closed"] = True
                self.history[key].append(candle)
                out.append(candle)
                candle = None
            if candle is None:
                candle = {
                    "type": "candle", "symbol": sym, "interval": name,
                    "open_time": open_time, "close_time": open_time + ms,
                    "open": price, "high": price, "low": price, "close": price,
                    "volume": 0.0, "trades": 0, "closed": False,
                }
                self.live[key] = candle
            candle["high"] = max(candle["high"], price)
            candle["low"] = min(candle["low"], price)
            candle["close"] = price
            candle["volume"] = round(candle["volume"] + size, sdp)
            candle["trades"] += 1
            out.append(dict(candle))
        return out

    def series(self, symbol: str, interval: str, limit: int) -> List[dict]:
        key = (symbol, interval)
        items = list(self.history[key])
        if key in self.live:
            items.append(self.live[key])
        return items[-limit:]


candles = CandleBook()


def build_order_book(symbol: str, mid: float) -> dict:
    cfg = INSTRUMENTS[symbol]
    pdp, sdp = cfg["price_dp"], cfg["size_dp"]
    spread = mid * SPREAD_PCT * simulator.spread_mult(symbol)
    best_bid = mid - spread / 2.0
    best_ask = mid + spread / 2.0
    tick = spread

    bids, asks = [], []
    for i in range(DEPTH_LEVELS):
        depth_factor = 1.0 + i * random.uniform(0.1, 0.4)
        bids.append({
            "price": round(best_bid - i * tick, pdp),
            "size": round(cfg["base_size"] * random.uniform(0.05, 0.6) * depth_factor, sdp),
        })
        asks.append({
            "price": round(best_ask + i * tick, pdp),
            "size": round(cfg["base_size"] * random.uniform(0.05, 0.6) * depth_factor, sdp),
        })

    return {
        "type": "orderbook",
        "symbol": symbol,
        "timestamp": _now_ms(),
        "volatility": simulator.modes[symbol],
        "bids": bids,
        "asks": asks,
    }


def build_trade(symbol: str, mid: float) -> dict:
    cfg = INSTRUMENTS[symbol]
    pdp, sdp = cfg["price_dp"], cfg["size_dp"]
    spread = mid * SPREAD_PCT * simulator.spread_mult(symbol)
    side = random.choice(["buy", "sell"])
    if side == "buy":
        price = mid + spread / 2.0 * random.uniform(0.2, 1.0)
    else:
        price = mid - spread / 2.0 * random.uniform(0.2, 1.0)
    size_mult = 1.0 + (abs(simulator.impulses[symbol]) * 60.0)
    return {
        "type": "trade",
        "symbol": symbol,
        "timestamp": _now_ms(),
        "price": round(price, pdp),
        "size": round(cfg["base_size"] * random.uniform(0.005, 0.15) * size_mult, sdp),
        "side": side,
    }


# ---------------------------------------------------------------------------
# Subscriptions
# ---------------------------------------------------------------------------
subscribers: Dict[str, Set["Subscription"]] = defaultdict(set)


class Subscription:
    """Streams market data for one symbol to one websocket connection."""

    def __init__(self, websocket: WebSocket, symbol: str, send_lock: asyncio.Lock,
                 channels: Set[str], candle_intervals: Set[str]):
        self.websocket = websocket
        self.symbol = symbol
        self.send_lock = send_lock
        self.channels = channels
        self.candle_intervals = candle_intervals
        self.task: Optional[asyncio.Task] = None

    def start(self):
        subscribers[self.symbol].add(self)
        self.task = asyncio.create_task(self._run())

    async def stop(self):
        subscribers[self.symbol].discard(self)
        if self.task:
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task

    async def send(self, payload: dict):
        async with self.send_lock:
            await self.websocket.send_json(payload)

    async def _run(self):
        try:
            while True:
                mid = simulator.step(self.symbol)
                if "orderbook" in self.channels:
                    await self.send(build_order_book(self.symbol, mid))
                if random.random() < 0.8:
                    trade = build_trade(self.symbol, mid)
                    updates = candles.on_trade(trade)
                    if "trade" in self.channels:
                        await self.send(trade)
                    if "candle" in self.channels:
                        for c in updates:
                            if c["interval"] in self.candle_intervals:
                                await self.send(c)
                delay = random.randint(MIN_INTERVAL_MS, MAX_INTERVAL_MS) / 1000.0
                await asyncio.sleep(delay)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.info("Stream for %s ended: %s", self.symbol, exc)


async def broadcast(symbol: str, payload: dict):
    for sub in list(subscribers.get(symbol, ())):
        with suppress(Exception):
            await sub.send(payload)


def _symbol_info(sym: str) -> dict:
    cfg = INSTRUMENTS[sym]
    return {
        "symbol": sym,
        "mid": round(simulator.mids[sym], cfg["price_dp"]),
        "start": cfg["start"],
        "volatility": simulator.modes[sym],
        "change_1m_pct": round(simulator.change_1m_pct(sym), 4),
        "price_dp": cfg["price_dp"],
        "size_dp": cfg["size_dp"],
        "dynamic": cfg.get("dynamic", False),
    }


def build_ticker() -> dict:
    return {
        "type": "ticker",
        "timestamp": _now_ms(),
        "markets": [
            {
                "symbol": sym,
                "mid": round(simulator.mids[sym], INSTRUMENTS[sym]["price_dp"]),
                "change_1m_pct": round(simulator.change_1m_pct(sym), 4),
                "volatility": simulator.modes[sym],
                "price_dp": INSTRUMENTS[sym]["price_dp"],
            }
            for sym in INSTRUMENTS
        ],
    }


async def market_clock():
    """Drifts markets nobody is streaming and records mid history for 1m change."""
    while True:
        for sym in list(INSTRUMENTS):
            if not subscribers.get(sym):
                simulator.step(sym)
            simulator.record(sym)
        await asyncio.sleep(CLOCK_INTERVAL_S)


async def ticker_stream(send):
    while True:
        await send(build_ticker())
        await asyncio.sleep(TICKER_INTERVAL_S)


def _validate_symbol(symbol: str) -> str:
    symbol = symbol.upper().strip()
    if not SYMBOL_RE.match(symbol):
        raise ValueError(f"Invalid symbol '{symbol}'. Expected format like 'ABC-USD'.")
    return symbol


async def _set_volatility(symbol: str, mode: str) -> dict:
    simulator.set_mode(symbol, mode)
    event = {
        "type": "market_event", "event": "volatility_changed",
        "symbol": symbol, "volatility": mode, "timestamp": _now_ms(),
    }
    await broadcast(symbol, event)
    return event


async def _spike(symbol: str, direction: str, magnitude_pct: float, persist: bool) -> dict:
    signed = magnitude_pct if direction == "up" else -magnitude_pct
    simulator.spike(symbol, signed, persist)
    event = {
        "type": "market_event", "event": "spike", "symbol": symbol,
        "direction": direction, "magnitude_pct": magnitude_pct,
        "persist": persist, "timestamp": _now_ms(),
    }
    await broadcast(symbol, event)
    return event


# ---------------------------------------------------------------------------
# Scenario scripts (timed sequences of spikes / volatility changes)
# ---------------------------------------------------------------------------
class ScenarioStep(BaseModel):
    delay_ms: int = Field(default=0, ge=0, le=600_000)
    action: Literal["spike", "set_volatility"]
    mode: Optional[Literal["calm", "normal", "volatile"]] = None
    direction: Optional[Literal["up", "down"]] = None
    magnitude_pct: float = Field(default=2.0, gt=0, le=50)
    persist: bool = False


class ScenarioBody(BaseModel):
    preset: Optional[str] = None
    name: Optional[str] = None
    steps: Optional[List[ScenarioStep]] = Field(default=None, max_length=50)


scenarios: Dict[str, dict] = {}


def _resolve_scenario(body: ScenarioBody) -> Tuple[str, List[dict]]:
    if body.preset:
        preset = SCENARIO_PRESETS.get(body.preset)
        if not preset:
            raise ValueError(f"Unknown preset. Use one of {list(SCENARIO_PRESETS)}.")
        return body.name or preset["name"], [dict(s) for s in preset["steps"]]
    if not body.steps:
        raise ValueError("Provide either 'preset' or a non-empty 'steps' list.")
    for s in body.steps:
        if s.action == "set_volatility" and not s.mode:
            raise ValueError("set_volatility steps require 'mode'.")
    return body.name or "Custom scenario", [s.model_dump() for s in body.steps]


def _scenario_event(symbol: str, event: str, **extra) -> dict:
    return {"type": "market_event", "event": event, "symbol": symbol, "timestamp": _now_ms(), **extra}


async def cancel_scenario(symbol: str) -> bool:
    state = scenarios.pop(symbol, None)
    if not state:
        return False
    state["task"].cancel()
    with suppress(asyncio.CancelledError):
        await state["task"]
    return True


async def start_scenario(symbol: str, name: str, steps: List[dict]) -> dict:
    await cancel_scenario(symbol)
    total = len(steps)
    state = {"name": name, "total": total, "index": 0, "started_at": _now_ms()}

    async def runner():
        try:
            await broadcast(symbol, _scenario_event(symbol, "scenario_started", name=name, total=total, steps=steps))
            for i, st in enumerate(steps, start=1):
                await asyncio.sleep(st["delay_ms"] / 1000.0)
                if st["action"] == "spike":
                    await _spike(symbol, st["direction"] or "up", st["magnitude_pct"], st["persist"])
                else:
                    await _set_volatility(symbol, st["mode"])
                state["index"] = i
                await broadcast(symbol, _scenario_event(symbol, "scenario_step", name=name, index=i, total=total, step=st))
            scenarios.pop(symbol, None)
            await broadcast(symbol, _scenario_event(symbol, "scenario_finished", name=name, total=total))
        except asyncio.CancelledError:
            await broadcast(symbol, _scenario_event(symbol, "scenario_cancelled", name=name, index=state["index"], total=total))
            raise

    state["task"] = asyncio.create_task(runner())
    scenarios[symbol] = state
    return {"symbol": symbol, "name": name, "total": total, "steps": steps}


def _scenario_status(symbol: str) -> Optional[dict]:
    state = scenarios.get(symbol)
    if not state:
        return None
    return {"name": state["name"], "index": state["index"], "total": state["total"], "started_at": state["started_at"]}


# ---------------------------------------------------------------------------
# REST API
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(_: FastAPI):
    clock = asyncio.create_task(market_clock())
    yield
    clock.cancel()
    for sym in list(scenarios):
        await cancel_scenario(sym)


app = FastAPI(title="Mock Crypto Exchange - Market Data", lifespan=lifespan)
api_router = APIRouter(prefix="/api")


class NewSymbol(BaseModel):
    symbol: str
    start_price: Optional[float] = Field(default=None, gt=0)


class VolatilityBody(BaseModel):
    mode: str


class SpikeBody(BaseModel):
    direction: str = "up"
    magnitude_pct: float = Field(default=2.0, gt=0, le=50)
    persist: bool = False


@api_router.get("/")
async def root():
    return {"message": "Mock Crypto Exchange market-data service is running"}


@api_router.get("/symbols")
async def symbols():
    return {
        "symbols": [_symbol_info(sym) for sym in INSTRUMENTS],
        "depth_levels": DEPTH_LEVELS,
        "spread_pct": SPREAD_PCT,
        "interval_ms": [MIN_INTERVAL_MS, MAX_INTERVAL_MS],
        "volatility_modes": list(VOLATILITY_MODES.keys()),
        "candle_intervals": list(CANDLE_INTERVALS.keys()),
        "channels": sorted(CHANNELS),
    }


@api_router.post("/symbols", status_code=201)
async def add_symbol(body: NewSymbol):
    try:
        sym = _validate_symbol(body.symbol)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if sym in INSTRUMENTS:
        raise HTTPException(status_code=409, detail=f"Symbol '{sym}' already exists.")
    register_instrument(sym, body.start_price)
    return _symbol_info(sym)


@api_router.post("/symbols/{symbol}/volatility")
async def set_volatility(symbol: str, body: VolatilityBody):
    sym = symbol.upper()
    if sym not in INSTRUMENTS:
        raise HTTPException(status_code=404, detail=f"Unknown symbol '{sym}'.")
    mode = body.mode.lower()
    if mode not in VOLATILITY_MODES:
        raise HTTPException(status_code=400, detail=f"Unknown mode. Use one of {list(VOLATILITY_MODES)}.")
    await _set_volatility(sym, mode)
    return _symbol_info(sym)


@api_router.post("/symbols/{symbol}/spike")
async def spike_symbol(symbol: str, body: SpikeBody):
    sym = symbol.upper()
    if sym not in INSTRUMENTS:
        raise HTTPException(status_code=404, detail=f"Unknown symbol '{sym}'.")
    direction = body.direction.lower()
    if direction not in ("up", "down"):
        raise HTTPException(status_code=400, detail="direction must be 'up' or 'down'.")
    return await _spike(sym, direction, body.magnitude_pct, body.persist)


@api_router.get("/candles/{symbol}")
async def get_candles(symbol: str, interval: str = DEFAULT_CANDLE_INTERVAL,
                      limit: int = Query(default=100, ge=1, le=CANDLE_HISTORY)):
    sym = symbol.upper()
    if sym not in INSTRUMENTS:
        raise HTTPException(status_code=404, detail=f"Unknown symbol '{sym}'.")
    if interval not in CANDLE_INTERVALS:
        raise HTTPException(status_code=400, detail=f"Unknown interval. Use one of {list(CANDLE_INTERVALS)}.")
    return {"symbol": sym, "interval": interval, "candles": candles.series(sym, interval, limit)}


@api_router.get("/ticker")
async def get_ticker():
    return build_ticker()


@api_router.get("/scenarios")
async def list_scenarios():
    return {
        "presets": [{"id": key, **preset} for key, preset in SCENARIO_PRESETS.items()],
        "running": {sym: _scenario_status(sym) for sym in scenarios},
    }


@api_router.post("/symbols/{symbol}/scenario", status_code=202)
async def run_scenario(symbol: str, body: ScenarioBody):
    sym = symbol.upper()
    if sym not in INSTRUMENTS:
        raise HTTPException(status_code=404, detail=f"Unknown symbol '{sym}'.")
    try:
        name, steps = _resolve_scenario(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return await start_scenario(sym, name, steps)


@api_router.get("/symbols/{symbol}/scenario")
async def scenario_status(symbol: str):
    sym = symbol.upper()
    if sym not in INSTRUMENTS:
        raise HTTPException(status_code=404, detail=f"Unknown symbol '{sym}'.")
    return {"symbol": sym, "running": _scenario_status(sym)}


@api_router.delete("/symbols/{symbol}/scenario")
async def stop_scenario(symbol: str):
    sym = symbol.upper()
    if sym not in INSTRUMENTS:
        raise HTTPException(status_code=404, detail=f"Unknown symbol '{sym}'.")
    cancelled = await cancel_scenario(sym)
    return {"symbol": sym, "cancelled": cancelled}


app.include_router(api_router)


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------
@app.websocket("/api/ws/market-data")
async def market_data_ws(websocket: WebSocket):
    """Client protocol (JSON messages):

        {"action": "subscribe", "symbol": "BTC-USD",
         "channels": ["orderbook","trade","candle"], "candle_intervals": ["1s","1m"],
         "start_price": 12.5}                       # start_price only used for new symbols
        {"action": "unsubscribe", "symbol": "BTC-USD"}
        {"action": "set_volatility", "symbol": "BTC-USD", "mode": "volatile"}
        {"action": "spike", "symbol": "BTC-USD", "direction": "down", "magnitude_pct": 3}
        {"action": "subscribe_ticker"} / {"action": "unsubscribe_ticker"}
        {"action": "run_scenario", "symbol": "BTC-USD", "preset": "news_day"}   # or "steps": [...]
        {"action": "cancel_scenario", "symbol": "BTC-USD"}
    """
    await websocket.accept()
    send_lock = asyncio.Lock()
    subscriptions: Dict[str, Subscription] = {}
    ticker_task: Optional[asyncio.Task] = None

    async def reply(payload: dict):
        async with send_lock:
            await websocket.send_json(payload)

    await reply({
        "type": "welcome",
        "message": "Connected to Mock Crypto Exchange market-data feed.",
        "available_symbols": list(INSTRUMENTS.keys()),
        "channels": sorted(CHANNELS),
        "candle_intervals": list(CANDLE_INTERVALS.keys()),
        "volatility_modes": list(VOLATILITY_MODES.keys()),
        "scenario_presets": list(SCENARIO_PRESETS.keys()),
        "timestamp": _now_ms(),
    })

    try:
        while True:
            msg = await websocket.receive_json()
            action = (msg.get("action") or msg.get("type") or "").lower()
            raw_symbol = (msg.get("symbol") or "")

            if action == "subscribe":
                try:
                    symbol = _validate_symbol(raw_symbol)
                except ValueError as exc:
                    await reply({"type": "error", "message": str(exc),
                                 "available_symbols": list(INSTRUMENTS.keys())})
                    continue
                if symbol in subscriptions:
                    await reply({"type": "info", "message": f"Already subscribed to {symbol}."})
                    continue
                created = False
                if symbol not in INSTRUMENTS:
                    start = msg.get("start_price")
                    register_instrument(symbol, float(start) if start else None)
                    created = True
                channels = {c.lower() for c in msg.get("channels") or CHANNELS} & CHANNELS
                intervals = {i for i in msg.get("candle_intervals") or [DEFAULT_CANDLE_INTERVAL]
                             if i in CANDLE_INTERVALS}
                sub = Subscription(websocket, symbol, send_lock, channels or set(CHANNELS), intervals)
                subscriptions[symbol] = sub
                sub.start()
                await reply({
                    "type": "subscribed", "symbol": symbol, "created": created,
                    "channels": sorted(sub.channels), "candle_intervals": sorted(intervals),
                    "instrument": _symbol_info(symbol), "timestamp": _now_ms(),
                    "scenario": _scenario_status(symbol),
                })

            elif action == "unsubscribe":
                symbol = raw_symbol.upper()
                sub = subscriptions.pop(symbol, None)
                if sub:
                    await sub.stop()
                    await reply({"type": "unsubscribed", "symbol": symbol, "timestamp": _now_ms()})
                else:
                    await reply({"type": "info", "message": f"Not subscribed to {symbol}."})

            elif action == "set_volatility":
                symbol = raw_symbol.upper()
                mode = (msg.get("mode") or "").lower()
                if symbol not in INSTRUMENTS:
                    await reply({"type": "error", "message": f"Unknown symbol '{symbol}'."})
                elif mode not in VOLATILITY_MODES:
                    await reply({"type": "error",
                                 "message": f"Unknown mode. Use one of {list(VOLATILITY_MODES)}."})
                else:
                    event = await _set_volatility(symbol, mode)
                    if symbol not in subscriptions:
                        await reply(event)

            elif action == "spike":
                symbol = raw_symbol.upper()
                direction = (msg.get("direction") or "up").lower()
                try:
                    magnitude = float(msg.get("magnitude_pct", 2.0))
                except (TypeError, ValueError):
                    magnitude = 0.0
                if symbol not in INSTRUMENTS:
                    await reply({"type": "error", "message": f"Unknown symbol '{symbol}'."})
                elif direction not in ("up", "down") or not 0 < magnitude <= 50:
                    await reply({"type": "error",
                                 "message": "direction must be 'up'/'down' and 0 < magnitude_pct <= 50."})
                else:
                    event = await _spike(symbol, direction, magnitude, bool(msg.get("persist", False)))
                    if symbol not in subscriptions:
                        await reply(event)

            elif action == "subscribe_ticker":
                if not ticker_task:
                    ticker_task = asyncio.create_task(ticker_stream(reply))
                await reply({"type": "ticker_subscribed", "timestamp": _now_ms()})

            elif action == "unsubscribe_ticker":
                if ticker_task:
                    ticker_task.cancel()
                    ticker_task = None
                await reply({"type": "ticker_unsubscribed", "timestamp": _now_ms()})

            elif action == "run_scenario":
                symbol = raw_symbol.upper()
                if symbol not in INSTRUMENTS:
                    await reply({"type": "error", "message": f"Unknown symbol '{symbol}'."})
                    continue
                try:
                    body = ScenarioBody.model_validate({k: msg.get(k) for k in ("preset", "name", "steps")})
                    name, steps = _resolve_scenario(body)
                except (ValidationError, ValueError) as exc:
                    await reply({"type": "error", "message": f"Invalid scenario: {exc}"})
                    continue
                result = await start_scenario(symbol, name, steps)
                await reply({"type": "scenario_accepted", **result, "timestamp": _now_ms()})

            elif action == "cancel_scenario":
                symbol = raw_symbol.upper()
                cancelled = await cancel_scenario(symbol)
                await reply({"type": "scenario_cancel", "symbol": symbol, "cancelled": cancelled, "timestamp": _now_ms()})

            else:
                await reply({
                    "type": "error",
                    "message": "Unknown action. Use subscribe, unsubscribe, set_volatility, spike, "
                               "subscribe_ticker, unsubscribe_ticker, run_scenario or cancel_scenario.",
                })

    except WebSocketDisconnect:
        logger.info("Client disconnected.")
    finally:
        if ticker_task:
            ticker_task.cancel()
        for sub in subscriptions.values():
            await sub.stop()


app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)
