import { useRef } from "react";
import { fmtNum, fmtPct } from "@/lib/format";

const WatchItem = ({ m, active, onSelect }) => {
  const prev = useRef(m.mid);
  const dir = Math.sign(m.mid - prev.current);
  prev.current = m.mid;
  const up = m.change_1m_pct >= 0;
  return (
    <button
      type="button"
      data-testid={`watchlist-item-${m.symbol}`}
      data-active={active}
      onClick={() => onSelect(m.symbol)}
      className={`flex h-full shrink-0 items-center gap-3 border-r border-[#18181B] px-3 transition-colors duration-200 hover:bg-[#171717] ${
        active ? "bg-[#121212] shadow-[inset_0_-2px_0_#4ADE80]" : ""
      }`}
    >
      <span className={`font-mono text-xs font-semibold ${active ? "text-white" : "text-[#A1A1AA]"}`}>{m.symbol}</span>
      <span
        className={`font-mono text-xs tabular-nums transition-colors duration-300 ${
          dir > 0 ? "text-[#4ADE80]" : dir < 0 ? "text-[#F87171]" : "text-[#E4E4E7]"
        }`}
      >
        {fmtNum(m.mid, m.price_dp)}
      </span>
      <span
        data-testid={`watchlist-change-${m.symbol}`}
        className={`rounded-sm px-1 font-mono text-[10px] tabular-nums ${
          up ? "bg-[#4ADE80]/10 text-[#4ADE80]" : "bg-[#F87171]/10 text-[#F87171]"
        }`}
      >
        {fmtPct(m.change_1m_pct, 2)}
      </span>
      {m.volatility !== "normal" && (
        <span className="text-[9px] uppercase tracking-wider text-[#FB923C]">{m.volatility}</span>
      )}
    </button>
  );
};

export const Watchlist = ({ markets, active, onSelect }) => (
  <div
    data-testid="watchlist"
    className="terminal-scroll flex h-9 shrink-0 items-stretch overflow-x-auto border-b border-[#27272A] bg-[#0C0C0C]"
  >
    <div className="flex shrink-0 items-center border-r border-[#18181B] px-3 text-[10px] uppercase tracking-[0.15em] text-[#52525B]">
      Markets <span className="ml-1 text-[#3F3F46]">1m</span>
    </div>
    {markets.length === 0 ? (
      <div className="flex items-center px-3 text-xs text-[#52525B]">Waiting for ticker…</div>
    ) : (
      markets.map((m) => <WatchItem key={m.symbol} m={m} active={m.symbol === active} onSelect={onSelect} />)
    )}
  </div>
);
