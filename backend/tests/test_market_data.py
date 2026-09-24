"""Backend tests for the Mock Crypto Exchange market-data service."""
import asyncio
import json
import os
import time
from collections import Counter

import pytest
import requests
import websockets

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
WS_URL = BASE_URL.replace("https://", "wss://").replace("http://", "ws://") + "/api/ws/market-data"

DEFAULT_SYMBOLS = {"BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD",
                   "DOGE-USD", "ADA-USD", "AVAX-USD", "LINK-USD"}


# ---------------- REST: /api/symbols ----------------
class TestSymbols:
    def test_list_symbols(self):
        r = requests.get(f"{BASE_URL}/api/symbols", timeout=10)
        assert r.status_code == 200
        data = r.json()
        for k in ("symbols", "volatility_modes", "candle_intervals", "channels"):
            assert k in data
        syms = {s["symbol"] for s in data["symbols"]}
        assert DEFAULT_SYMBOLS.issubset(syms)
        for s in data["symbols"]:
            for f in ("symbol", "mid", "start", "volatility", "price_dp", "size_dp", "dynamic"):
                assert f in s, f"missing field {f} in {s}"
        assert set(data["volatility_modes"]) >= {"calm", "normal", "volatile"}
        assert set(data["candle_intervals"]) >= {"1s", "5s", "15s", "1m"}
        assert set(data["channels"]) >= {"orderbook", "trade", "candle"}

    def test_create_symbol_lowercase_then_conflict(self):
        # Use a random tail to avoid persistence collisions across re-runs (env may keep state).
        sym_lower = f"tst{int(time.time()) % 10000}-usd"
        r = requests.post(f"{BASE_URL}/api/symbols", json={"symbol": sym_lower}, timeout=10)
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["symbol"] == sym_lower.upper()
        assert body["mid"] > 0
        assert body["dynamic"] is True
        # Duplicate -> 409
        r2 = requests.post(f"{BASE_URL}/api/symbols", json={"symbol": sym_lower}, timeout=10)
        assert r2.status_code == 409

    def test_create_symbol_invalid_format(self):
        r = requests.post(f"{BASE_URL}/api/symbols", json={"symbol": "bad"}, timeout=10)
        assert r.status_code == 400

    def test_create_symbol_with_start_price(self):
        sym = f"stp{int(time.time()) % 10000}-usd"
        r = requests.post(f"{BASE_URL}/api/symbols",
                          json={"symbol": sym, "start_price": 12.5}, timeout=10)
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["start"] == 12.5


# ---------------- REST: /api/symbols/{sym}/volatility ----------------
class TestVolatility:
    def test_set_volatility_ok(self):
        r = requests.post(f"{BASE_URL}/api/symbols/ETH-USD/volatility",
                          json={"mode": "volatile"}, timeout=10)
        assert r.status_code == 200
        assert r.json()["volatility"] == "volatile"
        # Verify reflected in listing
        r2 = requests.get(f"{BASE_URL}/api/symbols", timeout=10)
        eth = next(s for s in r2.json()["symbols"] if s["symbol"] == "ETH-USD")
        assert eth["volatility"] == "volatile"
        # Reset to normal to avoid impact on other tests
        requests.post(f"{BASE_URL}/api/symbols/ETH-USD/volatility",
                      json={"mode": "normal"}, timeout=10)

    def test_set_volatility_invalid_mode(self):
        r = requests.post(f"{BASE_URL}/api/symbols/ETH-USD/volatility",
                          json={"mode": "chaotic"}, timeout=10)
        assert r.status_code == 400

    def test_set_volatility_unknown_symbol(self):
        r = requests.post(f"{BASE_URL}/api/symbols/NOPE-USD/volatility",
                          json={"mode": "calm"}, timeout=10)
        assert r.status_code == 404


# ---------------- REST: /api/symbols/{sym}/spike ----------------
class TestSpike:
    def test_spike_ok(self):
        r = requests.post(f"{BASE_URL}/api/symbols/BTC-USD/spike",
                          json={"direction": "down", "magnitude_pct": 3}, timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert body["type"] == "market_event"
        assert body["event"] == "spike"
        assert body["direction"] == "down"
        assert body["magnitude_pct"] == 3

    def test_spike_invalid_direction(self):
        r = requests.post(f"{BASE_URL}/api/symbols/BTC-USD/spike",
                          json={"direction": "sideways", "magnitude_pct": 2}, timeout=10)
        assert r.status_code == 400

    def test_spike_magnitude_out_of_range(self):
        r = requests.post(f"{BASE_URL}/api/symbols/BTC-USD/spike",
                          json={"direction": "up", "magnitude_pct": 100}, timeout=10)
        assert r.status_code == 422


# ---------------- REST: /api/candles/{sym} ----------------
class TestCandles:
    def test_candles_invalid_interval(self):
        r = requests.get(f"{BASE_URL}/api/candles/BTC-USD?interval=2s&limit=5", timeout=10)
        assert r.status_code == 400

    def test_candles_unknown_symbol(self):
        r = requests.get(f"{BASE_URL}/api/candles/NOPE-USD?interval=1s&limit=5", timeout=10)
        assert r.status_code == 404

    def test_candles_after_ws_subscribe(self):
        """Subscribe over WS a few seconds so candles are produced, then GET history."""
        async def sub():
            async with websockets.connect(WS_URL) as ws:
                await ws.recv()  # welcome
                await ws.send(json.dumps({
                    "action": "subscribe", "symbol": "BTC-USD",
                    "candle_intervals": ["1s"],
                }))
                t0 = time.time()
                while time.time() - t0 < 3.5:
                    try:
                        await asyncio.wait_for(ws.recv(), timeout=2)
                    except asyncio.TimeoutError:
                        break
        asyncio.get_event_loop().run_until_complete(sub()) if False else asyncio.run(sub())

        r = requests.get(f"{BASE_URL}/api/candles/BTC-USD?interval=1s&limit=10", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data["symbol"] == "BTC-USD"
        assert data["interval"] == "1s"
        candles = data["candles"]
        assert isinstance(candles, list) and len(candles) > 0
        for c in candles:
            for f in ("open", "high", "low", "close", "volume", "trades",
                      "open_time", "close_time", "closed"):
                assert f in c
            assert c["high"] >= max(c["open"], c["close"])
            assert c["low"] <= min(c["open"], c["close"])


# ---------------- WebSocket ----------------
async def _recv_until(ws, deadline_s: float, stop_fn=None):
    msgs = []
    t0 = time.time()
    while time.time() - t0 < deadline_s:
        try:
            m = json.loads(await asyncio.wait_for(ws.recv(), timeout=deadline_s))
        except asyncio.TimeoutError:
            break
        msgs.append(m)
        if stop_fn and stop_fn(m):
            break
    return msgs


class TestWebSocket:
    def test_welcome_and_full_subscribe(self):
        async def run():
            async with websockets.connect(WS_URL) as ws:
                welcome = json.loads(await ws.recv())
                assert welcome["type"] == "welcome"
                for k in ("channels", "candle_intervals", "volatility_modes"):
                    assert k in welcome
                await ws.send(json.dumps({
                    "action": "subscribe", "symbol": "BTC-USD",
                    "candle_intervals": ["1s", "5s"],
                }))
                msgs = await _recv_until(ws, 6.0)
                return welcome, msgs
        welcome, msgs = asyncio.run(run())
        types = Counter(m["type"] for m in msgs)
        assert types.get("subscribed", 0) == 1
        sub = next(m for m in msgs if m["type"] == "subscribed")
        assert sub["created"] is False
        assert set(sub["channels"]) == {"orderbook", "trade", "candle"}
        assert set(sub["candle_intervals"]) == {"1s", "5s"}
        assert "instrument" in sub
        assert types["orderbook"] >= 1
        assert types["trade"] >= 1
        assert types["candle"] >= 1
        # Orderbook must have 10 bids/10 asks and volatility field
        ob = next(m for m in msgs if m["type"] == "orderbook")
        assert len(ob["bids"]) == 10
        assert len(ob["asks"]) == 10
        assert "volatility" in ob
        # Both intervals produced
        candle_intervals = {m["interval"] for m in msgs if m["type"] == "candle"}
        assert candle_intervals >= {"1s"}  # 5s may not close within 6s but 1s should arrive

    def test_subscribe_trade_channel_only(self):
        async def run():
            async with websockets.connect(WS_URL) as ws:
                await ws.recv()
                await ws.send(json.dumps({
                    "action": "subscribe", "symbol": "SOL-USD", "channels": ["trade"],
                }))
                return await _recv_until(ws, 4.0)
        msgs = asyncio.run(run())
        types = Counter(m["type"] for m in msgs)
        assert types["trade"] >= 1
        assert types.get("orderbook", 0) == 0
        assert types.get("candle", 0) == 0

    def test_subscribe_unknown_valid_symbol_creates(self):
        sym = f"ZZ{int(time.time()) % 100}-USD"

        async def run():
            async with websockets.connect(WS_URL) as ws:
                await ws.recv()
                await ws.send(json.dumps({"action": "subscribe", "symbol": sym}))
                return await _recv_until(
                    ws, 4.0,
                    stop_fn=lambda m: m["type"] in ("orderbook", "trade") and m.get("symbol") == sym,
                )
        msgs = asyncio.run(run())
        sub = next(m for m in msgs if m["type"] == "subscribed")
        assert sub["created"] is True
        assert sub["instrument"]["dynamic"] is True
        assert any(m["type"] in ("orderbook", "trade") and m["symbol"] == sym for m in msgs)

    def test_subscribe_invalid_symbol_returns_error(self):
        async def run():
            async with websockets.connect(WS_URL) as ws:
                await ws.recv()
                await ws.send(json.dumps({"action": "subscribe", "symbol": "bad"}))
                return json.loads(await asyncio.wait_for(ws.recv(), timeout=3))
        m = asyncio.run(run())
        assert m["type"] == "error"

    def test_ws_set_volatility_event(self):
        async def run():
            async with websockets.connect(WS_URL) as ws:
                await ws.recv()
                await ws.send(json.dumps({
                    "action": "subscribe", "symbol": "BTC-USD", "channels": ["orderbook"],
                }))
                # collect some baseline
                await _recv_until(ws, 1.5)
                await ws.send(json.dumps({
                    "action": "set_volatility", "symbol": "BTC-USD", "mode": "volatile",
                }))
                after = await _recv_until(ws, 3.0)
                await ws.send(json.dumps({
                    "action": "set_volatility", "symbol": "BTC-USD", "mode": "unknown",
                }))
                err = await _recv_until(ws, 2.0)
                # reset
                await ws.send(json.dumps({
                    "action": "set_volatility", "symbol": "BTC-USD", "mode": "normal",
                }))
                return after, err
        after, err = asyncio.run(run())
        assert any(m.get("type") == "market_event" and m.get("event") == "volatility_changed"
                   for m in after)
        assert any(m.get("type") == "orderbook" and m.get("volatility") == "volatile" for m in after)
        assert any(m.get("type") == "error" for m in err)

    def test_ws_spike_moves_price(self):
        async def run():
            async with websockets.connect(WS_URL) as ws:
                await ws.recv()
                await ws.send(json.dumps({
                    "action": "subscribe", "symbol": "ETH-USD", "channels": ["orderbook"],
                }))
                baseline_msgs = await _recv_until(ws, 1.5)
                base_mids = [(m["bids"][0]["price"] + m["asks"][0]["price"]) / 2
                             for m in baseline_msgs if m["type"] == "orderbook"]
                pre_mid = base_mids[-1] if base_mids else None
                await ws.send(json.dumps({
                    "action": "spike", "symbol": "ETH-USD",
                    "direction": "up", "magnitude_pct": 5,
                }))
                after = await _recv_until(ws, 2.5)
                after_mids = [(m["bids"][0]["price"] + m["asks"][0]["price"]) / 2
                              for m in after if m["type"] == "orderbook"]
                post_mid = after_mids[-1] if after_mids else None
                return pre_mid, post_mid, after
        pre_mid, post_mid, after = asyncio.run(run())
        assert any(m.get("type") == "market_event" and m.get("event") == "spike" for m in after)
        assert pre_mid and post_mid
        # Expect meaningful upward move (allow noise: > 1%)
        move_pct = (post_mid / pre_mid - 1) * 100
        assert move_pct > 1.0, f"expected upward spike, got {move_pct:.2f}%"

    def test_unsubscribe_and_unknown_action(self):
        async def run():
            async with websockets.connect(WS_URL) as ws:
                await ws.recv()
                await ws.send(json.dumps({
                    "action": "subscribe", "symbol": "XRP-USD", "channels": ["trade"],
                }))
                await _recv_until(ws, 1.5)
                await ws.send(json.dumps({"action": "unsubscribe", "symbol": "XRP-USD"}))
                # Give a bit for unsubscribe confirm + drain any in-flight
                unsub = await _recv_until(ws, 1.5)
                # After unsubscribe, wait and ensure no more XRP-USD messages
                post = await _recv_until(ws, 2.0)
                await ws.send(json.dumps({"action": "nope"}))
                err = await _recv_until(ws, 2.0)
                return unsub, post, err
        unsub, post, err = asyncio.run(run())
        assert any(m["type"] == "unsubscribed" for m in unsub)
        # Allow at most a couple in-flight XRP trade messages right after unsubscribe.
        xrp_after = [m for m in post if m.get("symbol") == "XRP-USD"]
        assert len(xrp_after) == 0, f"got {len(xrp_after)} XRP msgs after unsubscribe"
        assert any(m["type"] == "error" for m in err)


# ---------------- Regression: emit rate + spread ----------------
class TestRegression:
    def test_emit_rate_and_spread(self):
        async def run():
            async with websockets.connect(WS_URL) as ws:
                await ws.recv()
                # Ensure normal mode
                await ws.send(json.dumps({
                    "action": "set_volatility", "symbol": "LINK-USD", "mode": "normal",
                }))
                await ws.send(json.dumps({
                    "action": "subscribe", "symbol": "LINK-USD",
                    "channels": ["orderbook", "trade"],
                }))
                t0 = time.time()
                obs = []
                total = 0
                while time.time() - t0 < 3.0:
                    m = json.loads(await asyncio.wait_for(ws.recv(), timeout=2))
                    total += 1
                    if m["type"] == "orderbook":
                        obs.append(m)
                return total, obs, time.time() - t0
        total, obs, elapsed = asyncio.run(run())
        rate = total / elapsed
        assert rate >= 2, f"emit rate too low: {rate:.2f}/s"
        assert obs, "no orderbook messages received"
        # Median spread ~0.01% of mid
        spreads = []
        for m in obs:
            bid = m["bids"][0]["price"]
            ask = m["asks"][0]["price"]
            mid = (bid + ask) / 2
            spreads.append((ask - bid) / mid * 100)
        spreads.sort()
        median = spreads[len(spreads) // 2]
        # normal mode target ~0.01%; allow some variance
        assert 0.0 < median < 0.2, f"unexpected normal-mode spread median: {median:.4f}%"
