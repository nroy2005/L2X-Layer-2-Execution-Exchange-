import { useEffect, useState } from "react";
import axios from "axios";
import { Play, Plus, Square, X } from "lucide-react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { API, getFeed } from "@/hooks/useMarketFeed";

const selectCls = "h-8 rounded-sm border-[#27272A] bg-[#0C0C0C] font-mono text-xs text-white focus:ring-0 focus:ring-offset-0";
const contentCls = "rounded-sm border-[#27272A] bg-[#121212] text-white";
const itemCls = "font-mono text-xs focus:bg-[#171717] focus:text-white";

const describe = (s) =>
  s.action === "spike"
    ? `spike ${s.direction} ${s.magnitude_pct}%${s.persist ? " (persist)" : ""}`
    : `volatility → ${s.mode}`;

const StepRow = ({ index, step, onRemove }) => (
  <div data-testid="scenario-step-row" className="flex items-center gap-2 bg-[#0C0C0C] px-2 py-1 font-mono text-[11px]">
    <span className="w-4 text-[#52525B]">{index + 1}</span>
    <span className="w-14 tabular-nums text-[#A1A1AA]">+{(step.delay_ms / 1000).toFixed(1)}s</span>
    <span className={`flex-1 ${step.action === "spike" ? (step.direction === "up" ? "text-[#4ADE80]" : "text-[#F87171]") : "text-[#E4E4E7]"}`}>
      {describe(step)}
    </span>
    <button type="button" data-testid="scenario-step-remove-btn" onClick={onRemove} className="text-[#52525B] hover:text-white">
      <X className="h-3 w-3" />
    </button>
  </div>
);

const StepForm = ({ onAdd }) => {
  const [action, setAction] = useState("spike");
  const [delay, setDelay] = useState(3);
  const [direction, setDirection] = useState("up");
  const [magnitude, setMagnitude] = useState(3);
  const [mode, setMode] = useState("volatile");
  const submit = () =>
    onAdd(
      action === "spike"
        ? { delay_ms: Math.round(delay * 1000), action, direction, magnitude_pct: magnitude, persist: false }
        : { delay_ms: Math.round(delay * 1000), action, mode },
    );
  const numCls = "h-8 w-full bg-[#0C0C0C] px-2 font-mono text-xs tabular-nums text-white focus:outline-none";
  return (
    <div className="grid grid-cols-[64px_1fr_1fr_32px] gap-px bg-[#27272A]">
      <input data-testid="scenario-delay-input" type="number" min="0" step="0.5" value={delay} onChange={(e) => setDelay(Number(e.target.value))} className={numCls} title="Delay (s)" />
      <Select value={action} onValueChange={setAction}>
        <SelectTrigger data-testid="scenario-action-select" className={`${selectCls} border-0`}><SelectValue /></SelectTrigger>
        <SelectContent className={contentCls}>
          <SelectItem value="spike" className={itemCls}>spike</SelectItem>
          <SelectItem value="set_volatility" className={itemCls}>volatility</SelectItem>
        </SelectContent>
      </Select>
      {action === "spike" ? (
        <div className="flex gap-px">
          <Select value={direction} onValueChange={setDirection}>
            <SelectTrigger data-testid="scenario-direction-select" className={`${selectCls} w-16 border-0`}><SelectValue /></SelectTrigger>
            <SelectContent className={contentCls}>
              <SelectItem value="up" className={itemCls}>up</SelectItem>
              <SelectItem value="down" className={itemCls}>down</SelectItem>
            </SelectContent>
          </Select>
          <input data-testid="scenario-magnitude-input" type="number" min="0.5" max="50" step="0.5" value={magnitude} onChange={(e) => setMagnitude(Number(e.target.value))} className={numCls} title="Magnitude %" />
        </div>
      ) : (
        <Select value={mode} onValueChange={setMode}>
          <SelectTrigger data-testid="scenario-mode-select" className={`${selectCls} border-0`}><SelectValue /></SelectTrigger>
          <SelectContent className={contentCls}>
            {["calm", "normal", "volatile"].map((m) => <SelectItem key={m} value={m} className={itemCls}>{m}</SelectItem>)}
          </SelectContent>
        </Select>
      )}
      <button type="button" data-testid="scenario-add-step-btn" onClick={submit} className="flex items-center justify-center bg-[#1F1F23] text-[#E4E4E7] hover:bg-[#27272A]">
        <Plus className="h-3.5 w-3.5" />
      </button>
    </div>
  );
};

export const ScenarioBuilder = ({ symbol, scenario }) => {
  const [presets, setPresets] = useState([]);
  const [preset, setPreset] = useState("");
  const [steps, setSteps] = useState([]);
  const feed = getFeed();

  useEffect(() => {
    axios.get(`${API}/scenarios`).then((r) => setPresets(r.data.presets)).catch(() => {});
  }, []);

  const loadPreset = (id) => {
    setPreset(id);
    setSteps(presets.find((p) => p.id === id)?.steps ?? []);
  };
  const run = () => {
    if (!steps.length) return;
    const name = presets.find((p) => p.id === preset)?.name ?? "Custom scenario";
    feed.send({ action: "run_scenario", symbol, name, steps });
  };
  const cancel = () => feed.send({ action: "cancel_scenario", symbol });
  const totalSecs = steps.reduce((a, s) => a + s.delay_ms, 0) / 1000;

  return (
    <div data-testid="scenario-builder">
      <div className="mb-2 flex items-center justify-between">
        <p className="text-[10px] uppercase tracking-[0.15em] text-[#52525B]">Scenario script</p>
        <span className="font-mono text-[10px] tabular-nums text-[#52525B]">{steps.length} steps · {totalSecs.toFixed(1)}s</span>
      </div>

      {scenario ? (
        <div data-testid="scenario-running" className="mb-2 flex items-center justify-between bg-[#0C0C0C] px-2 py-1.5">
          <div>
            <p className="font-mono text-xs text-[#FB923C]">{scenario.name}</p>
            <p className="font-mono text-[10px] tabular-nums text-[#71717A]">step {scenario.index}/{scenario.total}</p>
          </div>
          <div className="flex items-center gap-2">
            <div className="h-1 w-20 bg-[#27272A]">
              <div className="h-1 bg-[#FB923C] transition-[width] duration-300" style={{ width: `${(scenario.index / scenario.total) * 100}%` }} />
            </div>
            <button type="button" data-testid="scenario-cancel-btn" onClick={cancel} className="flex h-7 items-center gap-1 bg-[#DC2626] px-2 text-[10px] font-semibold uppercase text-white hover:bg-[#F87171]">
              <Square className="h-3 w-3" /> Stop
            </button>
          </div>
        </div>
      ) : null}

      <Select value={preset} onValueChange={loadPreset}>
        <SelectTrigger data-testid="scenario-preset-select" className={`${selectCls} mb-2`}>
          <SelectValue placeholder="Load a preset…" />
        </SelectTrigger>
        <SelectContent className={contentCls}>
          {presets.map((p) => (
            <SelectItem key={p.id} value={p.id} data-testid={`scenario-preset-${p.id}`} className={itemCls}>
              {p.name} <span className="text-[#71717A]">· {p.steps.length} steps</span>
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <div className="mb-2 flex max-h-40 flex-col gap-px overflow-y-auto bg-[#27272A] terminal-scroll">
        {steps.length === 0 ? (
          <p data-testid="scenario-empty" className="bg-[#0C0C0C] px-2 py-2 text-[11px] text-[#52525B]">No steps. Load a preset or add steps below.</p>
        ) : (
          steps.map((s, i) => <StepRow key={i} index={i} step={s} onRemove={() => setSteps(steps.filter((_, j) => j !== i))} />)
        )}
      </div>

      <StepForm onAdd={(s) => setSteps([...steps, s])} />

      <button
        type="button"
        data-testid="scenario-run-btn"
        onClick={run}
        disabled={!steps.length || !symbol}
        className="mt-3 flex w-full items-center justify-center gap-1.5 bg-[#F59E0B] py-2.5 text-xs font-semibold uppercase tracking-wider text-black transition-colors duration-200 hover:bg-[#FBBF24] disabled:cursor-not-allowed disabled:opacity-40"
      >
        <Play className="h-4 w-4" /> Run scenario
      </button>
    </div>
  );
};
