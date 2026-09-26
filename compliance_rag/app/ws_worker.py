"""Background worker: mock exchange WebSocket trade stream -> SQLite."""

import asyncio
import json
import logging
from typing import Optional

import websockets
from websockets.exceptions import ConnectionClosed

from app.config import EXCHANGE_SYMBOLS, EXCHANGE_WS_URL
from app.database import SessionLocal, init_db
from app.models import ExecutedTrade

logger = logging.getLogger(__name__)


def _persist_trade(payload: dict) -> None:
    """Store a trade message from the mock exchange (type=trade)."""
    db = SessionLocal()
    try:
        row = ExecutedTrade(
            symbol=str(payload["symbol"]),
            timestamp_ms=int(payload["timestamp"]),
            price=float(payload["price"]),
            size=float(payload["size"]),
            side=str(payload["side"]),
        )
        db.add(row)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to persist trade: %s", payload)
    finally:
        db.close()


async def _consume_messages(ws) -> None:
    async for raw in ws:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if msg.get("type") != "trade":
            continue
        required = ("symbol", "timestamp", "price", "size", "side")
        if not all(k in msg for k in required):
            continue
        _persist_trade(msg)


async def _subscribe_all(ws, symbols: list[str]) -> None:
    for symbol in symbols:
        await ws.send(
            json.dumps(
                {
                    "action": "subscribe",
                    "symbol": symbol,
                    "channels": ["trade"],
                }
            )
        )


async def run_trade_ingestion(stop_event: asyncio.Event) -> None:
    """Connect to the mock exchange and log trades until stop_event is set."""
    init_db()
    backoff = 1.0
    while not stop_event.is_set():
        try:
            async with websockets.connect(EXCHANGE_WS_URL) as ws:
                logger.info("Connected to %s", EXCHANGE_WS_URL)
                backoff = 1.0
                await _subscribe_all(ws, EXCHANGE_SYMBOLS)
                consumer = asyncio.create_task(_consume_messages(ws))
                try:
                    while not stop_event.is_set():
                        await asyncio.sleep(0.5)
                finally:
                    consumer.cancel()
                    with asyncio.suppress(asyncio.CancelledError):
                        await consumer
        except ConnectionClosed as exc:
            logger.warning("WebSocket closed: %s", exc)
        except OSError as exc:
            logger.warning("WebSocket connection failed: %s", exc)
        except Exception:
            logger.exception("Trade ingestion error")

        if stop_event.is_set():
            break
        logger.info("Reconnecting in %.0fs...", backoff)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=backoff)
            break
        except asyncio.TimeoutError:
            pass
        backoff = min(backoff * 2, 30.0)


class TradeIngestionWorker:
    def __init__(self) -> None:
        self._stop = asyncio.Event()
        self._task: Optional[asyncio.Task] = None

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop.clear()
            self._task = asyncio.create_task(run_trade_ingestion(self._stop))

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            with asyncio.suppress(asyncio.CancelledError):
                await self._task
