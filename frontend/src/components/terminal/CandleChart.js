import { useEffect, useRef } from "react";
import axios from "axios";
import { createChart, CandlestickSeries, HistogramSeries, ColorType, CrosshairMode } from "lightweight-charts";
import { API, getFeed } from "@/hooks/useMarketFeed";
import { CANDLE_INTERVALS } from "@/lib/marketFeed";

const UP = "#4ADE80";
const DOWN = "#F87171";

const toBar = (c) => ({ time: c.open_time / 1000, open: c.open, high: c.high, low: c.low, close: c.close });
const toVol = (c) => ({
  time: c.open_time / 1000,
  value: c.volume,
  color: c.close >= c.open ? "rgba(74,222,128,0.45)" : "rgba(248,113,113,0.45)",
});

const CHART_OPTIONS = {
  autoSize: true,
  layout: {
    background: { type: ColorType.Solid, color: "#0C0C0C" },
    textColor: "#A1A1AA",
    fontFamily: "'JetBrains Mono', monospace",
    fontSize: 11,
    panes: { separatorColor: "#27272A", separatorHoverColor: "#3F3F46", enableResize: true },
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

const SERIES_OPTIONS = { upColor: UP, downColor: DOWN, borderVisible: false, wickUpColor: UP, wickDownColor: DOWN };
const VOLUME_OPTIONS = { priceFormat: { type: "volume" }, priceScaleId: "right", lastValueVisible: false, priceLineVisible: false };
const VOLUME_PANE_HEIGHT = 90;

export const CandleChart = ({ symbol, priceDp, interval, onIntervalChange }) => {
  const elRef = useRef(null);
  const chartRef = useRef(null);
  const seriesRef = useRef(null);
  const volumeRef = useRef(null);

  useEffect(() => {
    const chart = createChart(elRef.current, CHART_OPTIONS);
    chartRef.current = chart;
    seriesRef.current = chart.addSeries(CandlestickSeries, SERIES_OPTIONS, 0);
    volumeRef.current = chart.addSeries(HistogramSeries, VOLUME_OPTIONS, 1);
    chart.panes()[1]?.setHeight(VOLUME_PANE_HEIGHT);
    return () => chart.remove();
  }, []);

  useEffect(() => {
    const dp = priceDp ?? 2;
    seriesRef.current.applyOptions({ priceFormat: { type: "price", precision: dp, minMove: 10 ** -dp } });
  }, [priceDp]);

  useEffect(() => {
    if (!symbol) return undefined;
    const series = seriesRef.current;
    const volume = volumeRef.current;
    series.setData([]);
    volume.setData([]);
    let cancelled = false;
    let seeded = false;
    let lastTime = 0;
    const buffer = [];

    const apply = (c) => {
      const bar = toBar(c);
      if (bar.time < lastTime) return;
      lastTime = bar.time;
      series.update(bar);
      volume.update(toVol(c));
    };

    axios
      .get(`${API}/candles/${symbol}`, { params: { interval, limit: 300 } })
      .then((r) => {
        if (cancelled) return;
        const list = r.data.candles;
        series.setData(list.map(toBar));
        volume.setData(list.map(toVol));
        lastTime = list.length ? list[list.length - 1].open_time / 1000 : 0;
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
      if (seeded) apply(c);
      else buffer.push(c);
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
          <span className="ml-2 text-[10px] uppercase tracking-[0.15em] text-[#3F3F46]">+ Volume</span>
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
