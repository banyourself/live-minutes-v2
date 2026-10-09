import type { CSSProperties } from "react";

export default function MoneyInput({ value, onChange, placeholder = "250.00", label, style, disabled }: {
  value: string; onChange: (v: string) => void; placeholder?: string; label?: string; style?: CSSProperties; disabled?: boolean;
}) {
  return (
    <span className="money" style={style}>
      <span className="money-sign" aria-hidden="true">$</span>
      <input type="number" inputMode="decimal" min={0} step="0.01" value={value} disabled={disabled} placeholder={placeholder}
        aria-label={label} onChange={(e) => onChange(e.target.value)} />
    </span>
  );
}
