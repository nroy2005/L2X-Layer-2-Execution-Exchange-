import { useEffect, useRef } from "react";
import axios from "axios";
import { createChart, CandlestickSeries, ColorType, CrosshairMode } from "lightweight-charts";
import { API, getFeed } from "@/hooks/useMarketFeed";
import { CANDLE_INTERVALS } from "@/lib/marketFeed";

const toBar = (c) => ({ time: c.open_time / 1000, open: c.open, high: c.high, low: c.low, close: c.close });

const CHART_OPTIONS = {
  autoSize: true,
  layout: {
    background: { type: ColorType.Solid, color: "#0C0C0C" },
    textColor: "#A1A1AA",
    fontFamily: "'JetBrains Mono', monospace",
    fontSize: 11,
  },
  grid: { vertLines: { color: "#18181B" }, horzLines: { color: "#18181B" } },
  crosshair: { mode: CrosshairMode.Normal },
  rightPriceScale: { borderColor: "#27272A" },
  timeScale: { borderColor: "#27272A", timeVisible: true, secondsVisible: true, rightOffset: 4 },
  localization: {
    locale: "en-US",
    timeFormatter: (t) => new Date(t * 1000).toLocaleTimeString("en-GB"),
  },
};

const SERIES_OPTIONS = {
  upColor: "#4ADE80",
  downColor: "#F87171",
  borderVisible: false,
  wickUpColor: "#4ADE80",
  wickDownColor: "#F87171",
};

export const CandleChart = ({ symbol, priceDp, interval, onIntervalChange }) => {
  const elRef = useRef(null);
  const chartRef = useRef(null);
  const seriesRef = useRef(null);

  useEffect(() => {
    const chart = createChart(elRef.current, CHART_OPTIONS);
    chartRef.current = chart;
    seriesRef.current = chart.addSeries(CandlestickSeries, SERIES_OPTIONS);
    return () => chart.remove();
  }, []);

  useEffect(() => {
    const dp = priceDp ?? 2;
    seriesRef.current.applyOptions({ priceFormat: { type: "price", precision: dp, minMove: 10 ** -dp } });
  }, [priceDp]);

  useEffect(() => {
    if (!symbol) return undefined;
    const series = seriesRef.current;
    series.setData([]);
    let cancelled = false;
    let seeded = false;
    let lastTime = 0;
    const buffer = [];

    const apply = (bar) => {
      if (bar.time < lastTime) return;
      lastTime = bar.time;
      series.update(bar);
    };

    axios
      .get(`${API}/candles/${symbol}`, { params: { interval, limit: 300 } })
      .then((r) => {
        if (cancelled) return;
        const bars = r.data.candles.map(toBar);
        series.setData(bars);
        lastTime = bars.length ? bars[bars.length - 1].time : 0;
        seeded = true;
        buffer.forEach(apply);
        chartRef.current.timeScale().scrollToRealTime();
      })
      .catch(() => {
        seeded = true;
        buffer.forEach(apply);
      });

    const off = getFeed().on("candle", (c) => {
      if (c.symbol !== symbol || c.interval !== interval) return;
      const bar = toBar(c);
      if (seeded) apply(bar);
      else buffer.push(bar);
    });

    return () => {
      cancelled = true;
      off();
    };
  }, [symbol, interval]);

  return (
    <section data-testid="candle-chart-panel" className="flex h-full min-h-0 flex-col bg-[#0C0C0C]">
      <div className="flex h-9 shrink-0 items-center justify-between border-b border-[#18181B] px-3">
        <div className="flex items-center gap-2">
          <span className="text-[10px] uppercase tracking-[0.15em] text-[#52525B]">Candles</span>
          <span className="font-mono text-xs text-[#E4E4E7]">{symbol ?? "—"}</span>
        </div>
        <div className="flex gap-px bg-[#27272A]">
          {CANDLE_INTERVALS.map((iv) => (
            <button
              key={iv}
              type="button"
              data-testid={`interval-${iv}-btn`}
              onClick={() => onIntervalChange(iv)}
              className={`px-2.5 py-0.5 font-mono text-[11px] transition-colors duration-200 ${
                iv === interval ? "bg-[#27272A] text-white" : "bg-[#0C0C0C] text-[#71717A] hover:bg-[#171717]"
              }`}
            >
              {iv}
            </button>
          ))}
        </div>
      </div>
      <div ref={elRef} data-testid="candle-chart" className="min-h-0 flex-1" />
    </section>
  );
};
