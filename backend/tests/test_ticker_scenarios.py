"""Backend tests for new ticker + scenario features."""
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


# ---------------- REST: /api/ticker ----------------
class TestTicker:
    def test_ticker_shape(self):
        r = requests.get(f"{BASE_URL}/api/ticker", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data["type"] == "ticker"
        assert "timestamp" in data
        markets = data["markets"]
        assert isinstance(markets, list) and len(markets) >= 8
        for m in markets:
            for f in ("symbol", "mid", "change_1m_pct", "volatility", "price_dp"):
                assert f in m, f"missing {f} in {m}"
            assert isinstance(m["change_1m_pct"], (int, float))
            assert isinstance(m["mid"], (int, float)) and m["mid"] > 0

    def test_ticker_mids_drift_without_subscribe(self):
        r1 = requests.get(f"{BASE_URL}/api/ticker", timeout=10).json()
        time.sleep(3.0)
        r2 = requests.get(f"{BASE_URL}/api/ticker", timeout=10).json()
        mids1 = {m["symbol"]: m["mid"] for m in r1["markets"]}
        mids2 = {m["symbol"]: m["mid"] for m in r2["markets"]}
        changed = [s for s in mids1 if mids1[s] != mids2.get(s)]
        assert len(changed) >= 2, f"expected market clock to drift idle mids; changed={changed}"


# ---------------- REST: /api/scenarios and /api/symbols/{sym}/scenario ----------------
class TestScenariosREST:
    def test_list_presets(self):
        r = requests.get(f"{BASE_URL}/api/scenarios", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "presets" in data and "running" in data
        ids = {p["id"] for p in data["presets"]}
        assert {"news_day", "flash_crash", "pump_and_dump", "calm_drift"}.issubset(ids)
        for p in data["presets"]:
            assert p["name"] and p["description"] and isinstance(p["steps"], list)
        assert isinstance(data["running"], dict)

    def test_run_flash_crash_lifecycle(self):
        # Start
        r = requests.post(f"{BASE_URL}/api/symbols/SOL-USD/scenario",
                          json={"preset": "flash_crash"}, timeout=10)
        assert r.status_code == 202, r.text
        body = r.json()
        assert body["name"] == "Flash Crash"
        assert body["total"] == 5
        assert isinstance(body["steps"], list) and len(body["steps"]) == 5

        # Status shows running
        r2 = requests.get(f"{BASE_URL}/api/symbols/SOL-USD/scenario", timeout=10)
        assert r2.status_code == 200
        running = r2.json()["running"]
        assert running is not None
        assert running["name"] == "Flash Crash"
        assert "index" in running and "total" in running and running["total"] == 5

        # Cancel
        r3 = requests.delete(f"{BASE_URL}/api/symbols/SOL-USD/scenario", timeout=10)
        assert r3.status_code == 200
        assert r3.json()["cancelled"] is True

        # Cancel again -> false
        r4 = requests.delete(f"{BASE_URL}/api/symbols/SOL-USD/scenario", timeout=10)
        assert r4.status_code == 200
        assert r4.json()["cancelled"] is False

        # Reset vol to normal (flash_crash may have set volatile)
        requests.post(f"{BASE_URL}/api/symbols/SOL-USD/volatility",
                      json={"mode": "normal"}, timeout=10)

    def test_unknown_preset_400(self):
        r = requests.post(f"{BASE_URL}/api/symbols/SOL-USD/scenario",
                          json={"preset": "does_not_exist"}, timeout=10)
        assert r.status_code == 400

    def test_missing_mode_on_set_volatility_400(self):
        r = requests.post(f"{BASE_URL}/api/symbols/SOL-USD/scenario",
                          json={"steps": [{"action": "set_volatility"}]}, timeout=10)
        assert r.status_code == 400

    def test_invalid_magnitude_422(self):
        r = requests.post(
            f"{BASE_URL}/api/symbols/SOL-USD/scenario",
            json={"steps": [{"delay_ms": 0, "action": "spike",
                             "direction": "down", "magnitude_pct": 60}]},
            timeout=10,
        )
        assert r.status_code == 422

    def test_unknown_symbol_404(self):
        r = requests.post(f"{BASE_URL}/api/symbols/NOPE-USD/scenario",
                          json={"preset": "calm_drift"}, timeout=10)
        assert r.status_code == 404

    def test_custom_scenario_applies_and_finishes(self):
        target = "AVAX-USD"
        r = requests.post(
            f"{BASE_URL}/api/symbols/{target}/scenario",
            json={
                "name": "QA",
                "steps": [
                    {"delay_ms": 0, "action": "set_volatility", "mode": "volatile"},
                    {"delay_ms": 500, "action": "spike", "direction": "up", "magnitude_pct": 2},
                ],
            },
            timeout=10,
        )
        assert r.status_code == 202, r.text
        time.sleep(1.6)
        # Symbol volatility should have been set to volatile then still be volatile (no reset)
        syms = requests.get(f"{BASE_URL}/api/symbols", timeout=10).json()["symbols"]
        target_info = next(s for s in syms if s["symbol"] == target)
        assert target_info["volatility"] == "volatile"
        # Scenario should be finished
        st = requests.get(f"{BASE_URL}/api/symbols/{target}/scenario", timeout=10).json()
        assert st["running"] is None
        # Reset
        requests.post(f"{BASE_URL}/api/symbols/{target}/volatility",
                      json={"mode": "normal"}, timeout=10)


# ---------------- WebSocket: ticker + scenarios ----------------
async def _recv_until(ws, deadline_s, stop_fn=None):
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


class TestWebSocketTicker:
    def test_subscribe_unsubscribe_ticker(self):
        async def run():
            async with websockets.connect(WS_URL) as ws:
                await ws.recv()  # welcome
                await ws.send(json.dumps({"action": "subscribe_ticker"}))
                msgs = await _recv_until(ws, 3.5)
                await ws.send(json.dumps({"action": "unsubscribe_ticker"}))
                # Drain a moment
                await _recv_until(ws, 1.0, stop_fn=lambda m: m.get("type") == "ticker_unsubscribed")
                # After unsubscribe, we should not receive new ticker messages
                post = await _recv_until(ws, 2.5)
                return msgs, post
        msgs, post = asyncio.run(run())
        types = Counter(m["type"] for m in msgs)
        assert types.get("ticker_subscribed", 0) >= 1
        assert types.get("ticker", 0) >= 2, f"expected multiple ticker msgs, got {types}"
        ticker = next(m for m in msgs if m["type"] == "ticker")
        assert isinstance(ticker["markets"], list) and len(ticker["markets"]) >= 8
        assert not any(m.get("type") == "ticker" for m in post), \
            "ticker msgs continued after unsubscribe"


class TestWebSocketScenario:
    def test_run_and_cancel_calm_drift(self):
        async def run():
            async with websockets.connect(WS_URL) as ws:
                await ws.recv()  # welcome
                # Subscribe to BTC-USD
                await ws.send(json.dumps({
                    "action": "subscribe", "symbol": "BTC-USD",
                    "channels": ["orderbook"],
                }))
                # Wait for subscribed msg
                sub_msg = None
                t0 = time.time()
                while time.time() - t0 < 3:
                    m = json.loads(await asyncio.wait_for(ws.recv(), timeout=3))
                    if m.get("type") == "subscribed":
                        sub_msg = m
                        break
                assert sub_msg is not None
                assert "scenario" in sub_msg  # field present (null)
                # Run scenario
                await ws.send(json.dumps({
                    "action": "run_scenario", "symbol": "BTC-USD", "preset": "calm_drift",
                }))
                accepted_and_events = await _recv_until(
                    ws, 4.0,
                    stop_fn=lambda m: m.get("event") == "scenario_step",
                )
                # Cancel
                await ws.send(json.dumps({
                    "action": "cancel_scenario", "symbol": "BTC-USD",
                }))
                cancel_msgs = await _recv_until(
                    ws, 4.0,
                    stop_fn=lambda m: (
                        m.get("event") == "scenario_cancelled"
                        or m.get("type") == "scenario_cancel"
                    ),
                )
                # continue draining to also catch the market_event scenario_cancelled
                cancel_msgs += await _recv_until(
                    ws, 2.0,
                    stop_fn=lambda m: m.get("event") == "scenario_cancelled",
                )
                # Try invalid steps scenario -> error
                await ws.send(json.dumps({
                    "action": "run_scenario", "symbol": "BTC-USD",
                    "steps": [{"action": "set_volatility"}],
                }))
                err_msgs = await _recv_until(
                    ws, 2.0,
                    stop_fn=lambda m: m.get("type") == "error",
                )
                return sub_msg, accepted_and_events, cancel_msgs, err_msgs
        sub_msg, evts, cancel_msgs, err_msgs = asyncio.run(run())

        # scenario_accepted reply
        accepted = [m for m in evts if m.get("type") == "scenario_accepted"]
        assert accepted, f"no scenario_accepted, got types={[m.get('type') for m in evts]}"
        assert accepted[0]["name"] == "Calm Drift"
        assert accepted[0]["total"] == 2

        # scenario_started market_event
        started = [m for m in evts if m.get("event") == "scenario_started"]
        assert started, "no scenario_started event"
        assert started[0]["name"] == "Calm Drift"
        assert started[0]["total"] == 2

        # volatility_changed calm
        vol_changed = [m for m in evts if m.get("event") == "volatility_changed"]
        assert any(m.get("volatility") == "calm" for m in vol_changed)

        # scenario_step 1/2
        steps = [m for m in evts if m.get("event") == "scenario_step"]
        assert any(m.get("index") == 1 and m.get("total") == 2 for m in steps)

        # scenario_cancel reply
        cancel_replies = [m for m in cancel_msgs if m.get("type") == "scenario_cancel"]
        assert cancel_replies and cancel_replies[0]["cancelled"] is True

        # scenario_cancelled market_event
        assert any(m.get("event") == "scenario_cancelled" for m in cancel_msgs)

        # error for invalid scenario
        assert any(m.get("type") == "error" for m in err_msgs)

        # Reset BTC-USD volatility back to normal
        requests.post(f"{BASE_URL}/api/symbols/BTC-USD/volatility",
                      json={"mode": "normal"}, timeout=10)
