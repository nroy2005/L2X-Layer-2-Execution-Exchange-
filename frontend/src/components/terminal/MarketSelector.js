import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export const MarketSelector = ({ symbols, value, onChange }) => (
  <Select value={value ?? ""} onValueChange={onChange}>
    <SelectTrigger
      data-testid="market-selector"
      className="h-9 w-[150px] rounded-sm border-[#27272A] bg-[#121212] font-mono text-sm font-semibold tracking-wide text-white hover:bg-[#171717] focus:ring-1 focus:ring-[#3B82F6] focus:ring-offset-0"
    >
      <SelectValue placeholder="Market" />
    </SelectTrigger>
    <SelectContent className="rounded-sm border-[#27272A] bg-[#121212] text-white">
      {symbols.map((s) => (
        <SelectItem
          key={s.symbol}
          value={s.symbol}
          data-testid={`market-option-${s.symbol}`}
          className="font-mono text-sm focus:bg-[#171717] focus:text-white"
        >
          {s.symbol}
        </SelectItem>
      ))}
    </SelectContent>
  </Select>
);
