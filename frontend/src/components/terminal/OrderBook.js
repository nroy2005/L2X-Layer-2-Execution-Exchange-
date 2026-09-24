import { fmtNum, fmtPct } from "@/lib/format";

const BookRow = ({ level, cum, max, side, pdp, sdp }) => {
  const bid = side === "bid";
  return (
    <div
      data-testid={`orderbook-${side}-row`}
      className="relative grid grid-cols-3 px-2 py-0.5 font-mono text-xs tabular-nums hover:bg-[#171717]"
    >
      <span
        className="absolute inset-y-0 right-0"
        style={{ width: `${(cum / max) * 100}%`, background: bid ? "rgba(74,222,128,0.12)" : "rgba(248,113,113,0.12)" }}
      />
      <span className={`relative ${bid ? "text-[#4ADE80]" : "text-[#F87171]"}`}>{fmtNum(level.price, pdp)}</span>
      <span className="relative text-right text-[#E4E4E7]">{fmtNum(level.size, sdp)}</span>
      <span className="relative text-right text-[#71717A]">{fmtNum(cum, sdp)}</span>
    </div>
  );
};

const withCum = (levels) => {
  let acc = 0;
  return levels.map((l) => ({ level: l, cum: (acc += l.size) }));
};

export const OrderBook = ({ book, instrument }) => {
  const pdp = instrument?.price_dp ?? 2;
  const sdp = instrument?.size_dp ?? 4;
  const asks = book ? withCum(book.asks) : [];
  const bids = book ? withCum(book.bids) : [];
  const max = Math.max(asks.at(-1)?.cum ?? 0, bids.at(-1)?.cum ?? 0, 1e-9);
  const spread = book ? book.asks[0].price - book.bids[0].price : null;
  const mid = book ? (book.asks[0].price + book.bids[0].price) / 2 : null;

  return (
    <section data-testid="orderbook-panel" className="flex h-full min-h-0 flex-col bg-[#0C0C0C]">
      <div className="flex h-9 shrink-0 items-center justify-between border-b border-[#18181B] px-3">
        <span className="text-[10px] uppercase tracking-[0.15em] text-[#52525B]">Order Book</span>
        <span className="font-mono text-[10px] text-[#52525B]">10 levels</span>
      </div>
      <div className="grid grid-cols-3 border-b border-[#18181B] px-2 py-1 text-[10px] uppercase tracking-wider text-[#52525B]">
        <span>Price</span>
        <span className="text-right">Size</span>
        <span className="text-right">Total</span>
      </div>
      {!book ? (
        <div data-testid="orderbook-empty" className="flex flex-1 items-center justify-center text-xs text-[#52525B]">
          Waiting for depth…
        </div>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col justify-center overflow-hidden">
          <div className="flex flex-col-reverse">
            {asks.map(({ level, cum }) => (
              <BookRow key={level.price} level={level} cum={cum} max={max} side="ask" pdp={pdp} sdp={sdp} />
            ))}
          </div>
          <div
            data-testid="orderbook-spread-row"
            className="my-px flex items-center justify-between bg-[#18181B] px-2 py-1 font-mono text-xs tabular-nums"
          >
            <span className="text-[#E4E4E7]">{fmtNum(mid, pdp)}</span>
            <span className="text-[#71717A]">
              spread {fmtNum(spread, pdp)} <span className="text-[#52525B]">{fmtPct((spread / mid) * 100, 4)}</span>
            </span>
          </div>
          <div>
            {bids.map(({ level, cum }) => (
              <BookRow key={level.price} level={level} cum={cum} max={max} side="bid" pdp={pdp} sdp={sdp} />
            ))}
          </div>
        </div>
      )}
    </section>
  );
};
