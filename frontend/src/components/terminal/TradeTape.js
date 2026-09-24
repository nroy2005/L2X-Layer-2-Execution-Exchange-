import { fmtNum, fmtTime } from "@/lib/format";

const COLS = "grid grid-cols-[130px_100px_60px_1fr_1fr] px-3";

export const TradeTape = ({ trades, instrument }) => {
  const pdp = instrument?.price_dp ?? 2;
  const sdp = instrument?.size_dp ?? 4;
  return (
    <section data-testid="trade-tape-panel" className="flex h-full min-h-0 flex-col bg-[#0C0C0C]">
      <div className="flex h-9 shrink-0 items-center justify-between border-b border-[#18181B] px-3">
        <span className="text-[10px] uppercase tracking-[0.15em] text-[#52525B]">Trade Tape</span>
        <span data-testid="trade-count" className="font-mono text-[10px] text-[#52525B]">
          {trades.length} prints
        </span>
      </div>
      <div className={`${COLS} sticky top-0 border-b border-[#18181B] py-1 text-[10px] uppercase tracking-wider text-[#52525B]`}>
        <span>Timestamp</span>
        <span>Symbol</span>
        <span>Side</span>
        <span className="text-right">Size</span>
        <span className="text-right">Price</span>
      </div>
      <div className="terminal-scroll min-h-0 flex-1 overflow-y-auto">
        {trades.length === 0 ? (
          <div data-testid="trade-tape-empty" className="flex h-full items-center justify-center text-xs text-[#52525B]">
            Waiting for prints…
          </div>
        ) : (
          trades.map((t) => {
            const buy = t.side === "buy";
            return (
              <div
                key={`${t.timestamp}-${t.price}-${t.size}`}
                data-testid="trade-row"
                className={`${COLS} py-0.5 font-mono text-xs tabular-nums hover:bg-[#171717] ${buy ? "tape-flash-buy" : "tape-flash-sell"}`}
              >
                <span className="text-[#71717A]">{fmtTime(t.timestamp)}</span>
                <span className="text-[#A1A1AA]">{t.symbol}</span>
                <span className={buy ? "text-[#4ADE80]" : "text-[#F87171]"}>{buy ? "BUY" : "SELL"}</span>
                <span className="text-right text-[#E4E4E7]">{fmtNum(t.size, sdp)}</span>
                <span className={`text-right ${buy ? "text-[#4ADE80]" : "text-[#F87171]"}`}>{fmtNum(t.price, pdp)}</span>
              </div>
            );
          })
        )}
      </div>
    </section>
  );
};
