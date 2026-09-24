import { Activity, SlidersHorizontal } from "lucide-react";
import { MarketSelector } from "./MarketSelector";
import { fmtNum, fmtPct } from "@/lib/format";

const STATUS = {
  live: { dot: "bg-[#4ADE80]", label: "LIVE" },
  connecting: { dot: "bg-[#FACC15] animate-pulse", label: "CONNECTING" },
  reconnecting: { dot: "bg-[#F87171] animate-pulse", label: "RECONNECTING" },
};

const VOL = {
  calm: "text-[#60A5FA] border-[#60A5FA]/40",
  normal: "text-[#A1A1AA] border-[#3F3F46]",
  volatile: "text-[#FB923C] border-[#FB923C]/40",
};

export const Header = ({ snap, symbols, onSelect, onOpenPanel }) => {
  const dp = snap.instrument?.price_dp ?? 2;
  const dir = snap.mid == null || snap.prevMid == null ? 0 : Math.sign(snap.mid - snap.prevMid);
  const midColor = dir > 0 ? "text-[#4ADE80]" : dir < 0 ? "text-[#F87171]" : "text-white";
  const spread = snap.orderbook ? snap.orderbook.asks[0].price - snap.orderbook.bids[0].price : null;
  const spreadPct = spread != null && snap.mid ? (spread / snap.mid) * 100 : null;
  const st = STATUS[snap.status] ?? STATUS.connecting;

  return (
    <header
      data-testid="terminal-header"
      className="flex h-14 shrink-0 items-center justify-between border-b border-[#27272A] bg-[#0C0C0C] px-4"
    >
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2 pr-2">
          <Activity className="h-4 w-4 text-[#4ADE80]" />
          <span className="text-sm font-semibold tracking-[0.2em] text-white">TERMINAL</span>
        </div>
        <MarketSelector symbols={symbols} value={snap.symbol} onChange={onSelect} />
        <div className="flex items-baseline gap-3">
          <span
            data-testid="mid-price"
            className={`font-mono text-xl font-semibold tabular-nums transition-colors duration-300 ${midColor}`}
          >
            {fmtNum(snap.mid, dp)}
          </span>
          <span className="text-[10px] uppercase tracking-wider text-[#52525B]">mid</span>
        </div>
        <div className="hidden items-baseline gap-2 md:flex">
          <span className="text-[10px] uppercase tracking-wider text-[#52525B]">spread</span>
          <span data-testid="spread-value" className="font-mono text-xs tabular-nums text-[#A1A1AA]">
            {fmtNum(spread, dp)} <span className="text-[#52525B]">({fmtPct(spreadPct, 4)})</span>
          </span>
        </div>
        <span
          data-testid="volatility-badge"
          className={`rounded-sm border px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wider ${VOL[snap.volatility] ?? VOL.normal}`}
        >
          {snap.volatility}
        </span>
      </div>

      <div className="flex items-center gap-4">
        <span data-testid="msg-rate" className="hidden font-mono text-xs tabular-nums text-[#52525B] sm:inline">
          {snap.msgRate} msg/s
        </span>
        <div data-testid="connection-status" className="flex items-center gap-1.5">
          <span className={`h-2 w-2 rounded-full ${st.dot}`} />
          <span className="font-mono text-[10px] tracking-wider text-[#A1A1AA]">{st.label}</span>
        </div>
        <button
          type="button"
          data-testid="open-stress-panel-btn"
          onClick={onOpenPanel}
          className="flex h-8 items-center gap-2 rounded-sm border border-[#27272A] bg-[#121212] px-3 text-xs font-medium text-[#E4E4E7] transition-colors duration-200 hover:border-[#3F3F46] hover:bg-[#171717]"
        >
          <SlidersHorizontal className="h-3.5 w-3.5" />
          Stress Test
        </button>
      </div>
    </header>
  );
};
