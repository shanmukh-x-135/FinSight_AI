/**
 * Dependency-free SVG donut chart for categorical allocation (e.g. sectors).
 *
 * Uses the stroke-dasharray technique on a single circle — no chart library, so
 * it's small, themeable, and bug-free. The richer Plotly charts specified for
 * the dashboard arrive in Phase 7.
 */

export interface DonutSlice {
  label: string;
  value: number;
  percent: number;
}

// Accessible, distinct categorical palette.
const COLORS = [
  "#2563eb", // blue
  "#16a34a", // green
  "#f59e0b", // amber
  "#dc2626", // red
  "#7c3aed", // violet
  "#0891b2", // cyan
  "#db2777", // pink
  "#65a30d", // lime
];

export function DonutChart({ slices, size = 180 }: { slices: DonutSlice[]; size?: number }) {
  const stroke = 22;
  const radius = (size - stroke) / 2;
  const cx = size / 2;
  const cy = size / 2;
  const circumference = 2 * Math.PI * radius;

  let offset = 0;
  const total = slices.reduce((s, d) => s + d.value, 0);

  return (
    <div className="flex flex-wrap items-center gap-6">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img"
        aria-label="Sector allocation donut chart">
        <g transform={`rotate(-90 ${cx} ${cy})`}>
          {total > 0 &&
            slices.map((slice, i) => {
              const fraction = slice.value / total;
              const dash = fraction * circumference;
              const seg = (
                <circle
                  key={slice.label}
                  cx={cx}
                  cy={cy}
                  r={radius}
                  fill="none"
                  stroke={COLORS[i % COLORS.length]}
                  strokeWidth={stroke}
                  strokeDasharray={`${dash} ${circumference - dash}`}
                  strokeDashoffset={-offset}
                />
              );
              offset += dash;
              return seg;
            })}
        </g>
        <text
          x={cx}
          y={cy}
          textAnchor="middle"
          dominantBaseline="central"
          className="fill-foreground text-sm font-semibold"
        >
          {slices.length} {slices.length === 1 ? "sector" : "sectors"}
        </text>
      </svg>

      <ul className="flex flex-col gap-2 text-sm">
        {slices.map((slice, i) => (
          <li key={slice.label} className="flex items-center gap-2">
            <span
              className="inline-block h-3 w-3 rounded-sm"
              style={{ backgroundColor: COLORS[i % COLORS.length] }}
              aria-hidden
            />
            <span className="font-medium">{slice.label}</span>
            <span className="text-muted-foreground">{slice.percent.toFixed(1)}%</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
