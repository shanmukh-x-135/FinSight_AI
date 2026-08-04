/**
 * Heatmap — a grid of tiles coloured by a signed value (sector day-change %).
 * Green for positive, red for negative, intensity scaled by magnitude. Pure and
 * dependency-free (no chart lib) so it stays light and testable.
 */
export interface HeatmapCell {
  label: string;
  value: number | null;
  sub?: string;
}

/** Background colour for a signed %; null → neutral muted tile. */
function tileStyle(value: number | null): React.CSSProperties {
  if (value == null) return { backgroundColor: "var(--muted)" };
  const intensity = Math.min(Math.abs(value) / 3, 1); // saturate at ±3%
  const alpha = 0.12 + intensity * 0.5;
  // Tailwind green-600 / red-600 in rgb.
  const rgb = value > 0 ? "22, 163, 74" : value < 0 ? "220, 38, 38" : "120, 120, 120";
  return { backgroundColor: `rgba(${rgb}, ${alpha})` };
}

const fmtPct = (n: number | null) =>
  n == null ? "—" : `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`;

export interface HeatmapProps {
  cells: HeatmapCell[];
  emptyMessage?: string;
}

export function Heatmap({ cells, emptyMessage = "No sector data yet." }: HeatmapProps) {
  if (cells.length === 0) {
    return <p className="text-sm text-muted-foreground">{emptyMessage}</p>;
  }
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4">
      {cells.map((c) => (
        <div
          key={c.label}
          style={tileStyle(c.value)}
          className="rounded-lg p-3 ring-1 ring-foreground/5"
          title={c.sub}
        >
          <p className="truncate text-xs font-medium">{c.label}</p>
          <p className="mt-1 text-sm font-bold tabular-nums">{fmtPct(c.value)}</p>
          {c.sub && <p className="truncate text-[11px] text-muted-foreground">{c.sub}</p>}
        </div>
      ))}
    </div>
  );
}
