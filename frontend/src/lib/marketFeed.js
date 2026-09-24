const MAX_TRADES = 150;
const CHANNELS = ["orderbook", "trade", "candle"];
export const CANDLE_INTERVALS = ["1s", "5s"];

const initialSnapshot = {
  status: "connecting",
  symbol: null,
  instrument: null,
  orderbook: null,
  mid: null,
  prevMid: null,
  volatility: "normal",
  trades: [],
  lastTrade: null,
  msgRate: 0,
};

// Reconnecting WebSocket client. High-frequency ticks are written into a mutable
// pending state and flushed to React once per animation frame.
export class MarketFeed {
  constructor(url) {
    this.url = url;
    this.ws = null;
    this.attempt = 0;
    this.closed = false;
    this.symbol = null;
    this.handlers = new Map();
    this.subscribers = new Set();
    this.trades = [];
    this.tradesDirty = false;
    this.msgCount = 0;
    this.raf = 0;
    this.snapshot = { ...initialSnapshot };
    this.pending = { ...initialSnapshot };
    this.rateTimer = setInterval(() => {
      this.set({ msgRate: this.msgCount });
      this.msgCount = 0;
    }, 1000);
    this.connect();
  }

  set(patch) {
    Object.assign(this.pending, patch);
    if (!this.raf) this.raf = requestAnimationFrame(() => this.flush());
  }

  flush() {
    this.raf = 0;
    const trades = this.tradesDirty ? this.trades.slice() : this.snapshot.trades;
    this.tradesDirty = false;
    this.snapshot = { ...this.pending, trades };
    this.subscribers.forEach((fn) => fn());
  }

  connect() {
    if (this.closed) return;
    this.set({ status: this.attempt ? "reconnecting" : "connecting" });
    const ws = new WebSocket(this.url);
    this.ws = ws;
    ws.onopen = () => {
      this.attempt = 0;
      this.set({ status: "live" });
      if (this.symbol) this.sendSubscribe(this.symbol);
    };
    ws.onmessage = (e) => this.handle(JSON.parse(e.data));
    ws.onerror = () => ws.close();
    ws.onclose = () => {
      if (this.closed) return;
      this.set({ status: "reconnecting" });
      const delay = Math.min(1000 * 2 ** this.attempt, 10000);
      this.attempt += 1;
      this.timer = setTimeout(() => this.connect(), delay);
    };
  }

  handle(m) {
    this.msgCount += 1;
    const forActive = m.symbol === this.symbol;
    switch (m.type) {
      case "orderbook":
        if (!forActive) return;
        {
          const mid = (m.bids[0].price + m.asks[0].price) / 2;
          this.set({ orderbook: m, mid, prevMid: this.pending.mid ?? mid, volatility: m.volatility });
        }
        break;
      case "trade":
        if (!forActive) return;
        this.trades.unshift(m);
        if (this.trades.length > MAX_TRADES) this.trades.length = MAX_TRADES;
        this.tradesDirty = true;
        this.set({ lastTrade: m });
        break;
      case "subscribed":
        if (forActive) this.set({ instrument: m.instrument, volatility: m.instrument.volatility });
        break;
      case "market_event":
        if (forActive && m.event === "volatility_changed") this.set({ volatility: m.volatility });
        break;
      default:
        break;
    }
    this.emit(m.type, m);
  }

  emit(type, payload) {
    const set = this.handlers.get(type);
    if (set) set.forEach((fn) => fn(payload));
  }

  on(type, fn) {
    if (!this.handlers.has(type)) this.handlers.set(type, new Set());
    this.handlers.get(type).add(fn);
    return () => this.handlers.get(type)?.delete(fn);
  }

  send(obj) {
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(obj));
  }

  sendSubscribe(symbol) {
    this.send({ action: "subscribe", symbol, channels: CHANNELS, candle_intervals: CANDLE_INTERVALS });
  }

  subscribe(symbol) {
    if (!symbol || symbol === this.symbol) return;
    if (this.symbol) this.send({ action: "unsubscribe", symbol: this.symbol });
    this.symbol = symbol;
    this.trades = [];
    this.tradesDirty = true;
    this.set({ symbol, orderbook: null, mid: null, prevMid: null, instrument: null, lastTrade: null });
    this.sendSubscribe(symbol);
  }

  destroy() {
    this.closed = true;
    clearInterval(this.rateTimer);
    clearTimeout(this.timer);
    if (this.raf) cancelAnimationFrame(this.raf);
    this.ws?.close();
  }
}
