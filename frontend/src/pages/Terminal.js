import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Header } from "@/components/terminal/Header";
import { Watchlist } from "@/components/terminal/Watchlist";
import { CandleChart } from "@/components/terminal/CandleChart";
import { OrderBook } from "@/components/terminal/OrderBook";
import { TradeTape } from "@/components/terminal/TradeTape";
import { StressPanel } from "@/components/terminal/StressPanel";
import { API, getFeed, useFeedSnapshot } from "@/hooks/useMarketFeed";

const SYMBOL_KEY = "terminal.symbol";

export default function Terminal() {
  const feed = getFeed();
  const snap = useFeedSnapshot();
  const [symbols, setSymbols] = useState([]);
  const [candleInterval, setCandleInterval] = useState("1s");
  const [panelOpen, setPanelOpen] = useState(false);

  const loadSymbols = useCallback(() => axios.get(`${API}/symbols`).then((r) => r.data.symbols), []);

  useEffect(() => {
    loadSymbols().then((list) => {
      setSymbols(list);
      const saved = localStorage.getItem(SYMBOL_KEY);
      feed.subscribe(list.some((s) => s.symbol === saved) ? saved : list[0]?.symbol);
    });
  }, [feed, loadSymbols]);

  useEffect(
    () =>
      feed.on("market_event", (m) => {
        if (m.event === "volatility_changed") toast(`${m.symbol} volatility → ${m.volatility.toUpperCase()}`);
        else if (m.event === "spike")
          toast.warning(`${m.symbol} spike ${m.direction.toUpperCase()} ${m.magnitude_pct}%${m.persist ? " (persist)" : ""}`);
        else if (m.event === "scenario_started") toast(`${m.symbol} scenario "${m.name}" started · ${m.total} steps`);
        else if (m.event === "scenario_finished") toast.success(`${m.symbol} scenario "${m.name}" finished`);
        else if (m.event === "scenario_cancelled") toast(`${m.symbol} scenario "${m.name}" stopped`);
      }),
    [feed],
  );

  const select = (sym) => {
    localStorage.setItem(SYMBOL_KEY, sym);
    feed.subscribe(sym);
  };

  const onSymbolAdded = async (sym) => {
    setSymbols(await loadSymbols());
    select(sym);
    setPanelOpen(false);
  };

  return (
    <div data-testid="terminal-page" className="flex h-screen w-screen flex-col overflow-hidden bg-[#27272A] text-white">
      <Header snap={snap} symbols={symbols} onSelect={select} onOpenPanel={() => setPanelOpen(true)} />
      <Watchlist markets={snap.ticker} active={snap.symbol} onSelect={select} />
      <main className="flex min-h-0 flex-1 flex-col gap-px lg:flex-row">
        <div className="flex min-h-0 flex-1 flex-col gap-px">
          <div className="min-h-0 flex-1">
            <CandleChart
              symbol={snap.symbol}
              priceDp={snap.instrument?.price_dp}
              interval={candleInterval}
              onIntervalChange={setCandleInterval}
            />
          </div>
          <div className="h-[35%] min-h-[160px]">
            <TradeTape trades={snap.trades} instrument={snap.instrument} />
          </div>
        </div>
        <aside className="h-[40vh] shrink-0 lg:h-auto lg:w-[340px]">
          <OrderBook book={snap.orderbook} instrument={snap.instrument} />
        </aside>
      </main>
      <StressPanel open={panelOpen} onOpenChange={setPanelOpen} snap={snap} onSymbolAdded={onSymbolAdded} />
    </div>
  );
}
