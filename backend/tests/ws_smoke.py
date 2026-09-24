import asyncio, json, os, sys
from collections import Counter
import websockets

BASE = os.environ["REACT_APP_BACKEND_URL"].replace("https://", "wss://").replace("http://", "ws://")


async def main():
    async with websockets.connect(f"{BASE}/api/ws/market-data") as ws:
        print(json.loads(await ws.recv())["type"])
        await ws.send(json.dumps({"action": "subscribe", "symbol": "BTC-USD", "candle_intervals": ["1s", "5s"]}))
        await ws.send(json.dumps({"action": "subscribe", "symbol": "PEPE-USD"}))
        await ws.send(json.dumps({"action": "set_volatility", "symbol": "BTC-USD", "mode": "volatile"}))
        await ws.send(json.dumps({"action": "spike", "symbol": "BTC-USD", "direction": "down", "magnitude_pct": 3}))
        counts = Counter()
        first_mid = last_mid = None
        closed = 0
        t0 = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - t0 < 4:
            m = json.loads(await asyncio.wait_for(ws.recv(), 5))
            counts[(m["type"], m.get("symbol"), m.get("interval"))] += 1
            if m["type"] in ("subscribed", "market_event", "error"):
                print(m)
            if m["type"] == "candle" and m["closed"]:
                closed += 1
            if m["type"] == "orderbook" and m["symbol"] == "BTC-USD":
                mid = (m["bids"][0]["price"] + m["asks"][0]["price"]) / 2
                first_mid = first_mid or mid
                last_mid = mid
        for k, v in sorted(counts.items(), key=str):
            print(k, v)
        print("closed candles:", closed, "BTC move %:", round((last_mid / first_mid - 1) * 100, 2))


asyncio.run(main())
