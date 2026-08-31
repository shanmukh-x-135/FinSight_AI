import { DataTable, type Column } from "@/components/DataTable";
import { DataState, SectionHeader, StatusBadge, TrendValue } from "@/components/workspace";
import type { SectorRotation as SectorRotationRow } from "@/lib/api";
import { pct } from "@/lib/utils";

const regimeTone = {
  leader: "positive",
  improving: "positive",
  weakening: "warning",
  laggard: "negative",
  mixed: "neutral",
  unavailable: "neutral",
} as const;

export function SectorRotation({ rows }: { rows: SectorRotationRow[] }) {
  if (rows.length === 0) {
    return <DataState kind="empty" title="Sector rotation unavailable" description="At least one priced sector is required for the selected universe." />;
  }
  const columns: Column<SectorRotationRow>[] = [
    { key: "sector", header: "Sector", render: (row) => <span className="font-medium">{row.sector}<span className="ml-1 text-[10px] font-normal text-muted-foreground">({row.stock_count})</span></span> },
    { key: "1d", header: "1D", align: "right", render: (row) => <TrendValue compact value={row.return_1d}>{pct(row.return_1d)}</TrendValue> },
    { key: "5d", header: "5D", align: "right", render: (row) => <TrendValue compact value={row.return_5d}>{pct(row.return_5d)}</TrendValue> },
    { key: "20d", header: "20D", align: "right", render: (row) => <TrendValue compact value={row.return_20d}>{pct(row.return_20d)}</TrendValue> },
    { key: "regime", header: "Momentum", render: (row) => <StatusBadge label={row.momentum_regime} tone={regimeTone[row.momentum_regime]} /> },
  ];
  return (
    <div className="space-y-3">
      <SectionHeader title="Sector rotation" description="Equal-weight sector returns across 1, 5, and 20 trading sessions." />
      <DataTable columns={columns} rows={rows} rowKey={(row) => row.sector} caption="Sector rotation performance windows and momentum regimes" />
    </div>
  );
}
