import { useState } from "react";
import axios from "axios";
import { ArrowDownRight, ArrowUpRight, Plus } from "lucide-react";
import { toast } from "sonner";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { API, getFeed } from "@/hooks/useMarketFeed";

const MODES = ["calm", "normal", "volatile"];

const Label = ({ children }) => (
  <p className="mb-2 text-[10px] uppercase tracking-[0.15em] text-[#52525B]">{children}</p>
);

export const StressPanel = ({ open, onOpenChange, snap, onSymbolAdded }) => {
  const [magnitude, setMagnitude] = useState(2);
  const [persist, setPersist] = useState(false);
  const [newSymbol, setNewSymbol] = useState("");
  const [adding, setAdding] = useState(false);
  const feed = getFeed();
  const symbol = snap.symbol;

  const setMode = (mode) => feed.send({ action: "set_volatility", symbol, mode });
  const spike = (direction) => feed.send({ action: "spike", symbol, direction, magnitude_pct: magnitude, persist });

  const addMarket = async (e) => {
    e.preventDefault();
    const sym = newSymbol.trim().toUpperCase();
    if (!sym) return;
    setAdding(true);
    try {
      const r = await axios.post(`${API}/symbols`, { symbol: sym });
      toast.success(`${r.data.symbol} listed @ ${r.data.start}`);
      setNewSymbol("");
      onSymbolAdded(r.data.symbol);
    } catch (err) {
      toast.error(err.response?.data?.detail ?? "Failed to add market");
    } finally {
      setAdding(false);
    }
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        data-testid="stress-panel"
        className="w-[340px] border-l border-[#27272A] bg-[#121212] p-5 text-white sm:max-w-[340px]"
      >
        <SheetHeader className="mb-6 text-left">
          <SheetTitle className="text-base font-medium tracking-tight text-white">Stress Test</SheetTitle>
          <SheetDescription className="text-xs text-[#A1A1AA]">
            Drive the simulator for <span className="font-mono text-white">{symbol ?? "—"}</span>
          </SheetDescription>
        </SheetHeader>

        <div className="space-y-7">
          <div>
            <Label>Volatility mode</Label>
            <div className="grid grid-cols-3 gap-px bg-[#27272A]">
              {MODES.map((m) => (
                <button
                  key={m}
                  type="button"
                  data-testid={`volatility-${m}-btn`}
                  onClick={() => setMode(m)}
                  className={`py-2 font-mono text-xs uppercase tracking-wider transition-colors duration-200 ${
                    snap.volatility === m ? "bg-[#27272A] text-white" : "bg-[#121212] text-[#71717A] hover:bg-[#171717]"
                  }`}
                >
                  {m}
                </button>
              ))}
            </div>
          </div>

          <div>
            <div className="mb-2 flex items-center justify-between">
              <Label>Spike magnitude</Label>
              <span data-testid="spike-magnitude-value" className="font-mono text-xs tabular-nums text-white">
                {magnitude.toFixed(1)}%
              </span>
            </div>
            <Slider
              data-testid="spike-magnitude-slider"
              min={0.5}
              max={20}
              step={0.5}
              value={[magnitude]}
              onValueChange={([v]) => setMagnitude(v)}
            />
            <div className="mt-4 flex items-center justify-between">
              <div>
                <p className="text-xs text-[#E4E4E7]">Persist (re-anchor price)</p>
                <p className="text-[11px] text-[#52525B]">Off = flash move that mean-reverts</p>
              </div>
              <Switch data-testid="spike-persist-switch" checked={persist} onCheckedChange={setPersist} />
            </div>
            <div className="mt-4 grid grid-cols-2 gap-2">
              <button
                type="button"
                data-testid="spike-up-btn"
                onClick={() => spike("up")}
                className="flex items-center justify-center gap-1.5 bg-[#16A34A] py-2.5 text-xs font-semibold uppercase tracking-wider text-black transition-colors duration-200 hover:bg-[#4ADE80]"
              >
                <ArrowUpRight className="h-4 w-4" /> Spike up
              </button>
              <button
                type="button"
                data-testid="spike-down-btn"
                onClick={() => spike("down")}
                className="flex items-center justify-center gap-1.5 bg-[#DC2626] py-2.5 text-xs font-semibold uppercase tracking-wider text-white transition-colors duration-200 hover:bg-[#F87171]"
              >
                <ArrowDownRight className="h-4 w-4" /> Spike down
              </button>
            </div>
          </div>

          <form onSubmit={addMarket}>
            <Label>Add market</Label>
            <div className="flex gap-px bg-[#27272A]">
              <input
                data-testid="add-market-input"
                value={newSymbol}
                onChange={(e) => setNewSymbol(e.target.value)}
                placeholder="e.g. PEPE-USD"
                className="min-w-0 flex-1 bg-[#0C0C0C] px-3 py-2 font-mono text-xs uppercase text-white placeholder:normal-case placeholder:text-[#52525B] focus:outline-none"
              />
              <button
                type="submit"
                data-testid="add-market-btn"
                disabled={adding}
                className="flex items-center gap-1 bg-[#1F1F23] px-3 text-xs text-[#E4E4E7] transition-colors duration-200 hover:bg-[#27272A] disabled:opacity-50"
              >
                <Plus className="h-3.5 w-3.5" /> List
              </button>
            </div>
            <p className="mt-1.5 text-[11px] text-[#52525B]">Start price is generated from the symbol name.</p>
          </form>
        </div>
      </SheetContent>
    </Sheet>
  );
};
