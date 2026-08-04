import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { EconomicCalendar, EconomicEvent, TechnicalSummary } from "@/lib/api";

const eventDate = new Intl.DateTimeFormat("en-IN", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "Asia/Kolkata",
});

const importanceLabel = (importance: number) =>
  importance >= 3 ? "High impact" : importance === 2 ? "Medium impact" : "Low impact";

export function TechnicalSummaryCard({ summary }: { summary: TechnicalSummary | null }) {
  const metrics = summary
    ? [
        ["Average RSI", summary.average_rsi?.toFixed(1) ?? "—"],
        ["RSI bullish", String(summary.bullish_rsi_count)],
        ["Above EMA20", String(summary.above_ema20_count)],
        ["Above EMA50", String(summary.above_ema50_count)],
        ["MACD positive", String(summary.positive_macd_count)],
        [
          "Average ATR",
          summary.average_atr_percent == null
            ? "—"
            : `${summary.average_atr_percent.toFixed(2)}%`,
        ],
      ]
    : [];
  return (
    <Card>
      <CardHeader className="border-b">
        <CardTitle>Technical Summary</CardTitle>
        <p className="text-xs text-muted-foreground">
          {summary?.as_of
            ? `${summary.stocks_with_indicators} stocks · ${summary.as_of}`
            : "Latest market-wide indicator snapshot"}
        </p>
      </CardHeader>
      <CardContent>
        {metrics.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No indicator snapshot is available yet.
          </p>
        ) : (
          <dl className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-3">
            {metrics.map(([label, value]) => (
              <div key={label}>
                <dt className="text-xs text-muted-foreground">{label}</dt>
                <dd className="mt-1 text-base font-semibold tabular-nums">{value}</dd>
              </div>
            ))}
          </dl>
        )}
        {summary && (summary.overbought_count > 0 || summary.oversold_count > 0) && (
          <p className="mt-4 border-t pt-3 text-xs text-muted-foreground">
            Extremes: {summary.overbought_count} overbought ·{" "}
            {summary.oversold_count} oversold
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function EventCard({ event }: { event: EconomicEvent }) {
  return (
    <li className="w-72 shrink-0 rounded-lg border border-foreground/10 p-4">
      <div className="flex items-start justify-between gap-3">
        <time className="text-xs text-muted-foreground" dateTime={event.date}>
          {eventDate.format(new Date(event.date))}
        </time>
        <span className="shrink-0 rounded bg-muted px-2 py-0.5 text-[10px] font-medium">
          {importanceLabel(event.importance)}
        </span>
      </div>
      <p className="mt-3 font-semibold">{event.name}</p>
      <p className="text-xs text-muted-foreground">{event.category}</p>
      {event.source && (
        <p className="mt-1 truncate text-[11px] text-muted-foreground">
          Source: {event.source}
        </p>
      )}
      <dl className="mt-4 grid grid-cols-3 gap-2 text-center text-xs">
        {[
          ["Actual", event.actual],
          ["Forecast", event.forecast],
          ["Prior", event.previous],
        ].map(([label, value]) => (
            <div key={label}>
              <dt className="text-muted-foreground">{label}</dt>
              <dd className="mt-1 font-medium tabular-nums">{value ?? "—"}</dd>
            </div>
        ))}
      </dl>
    </li>
  );
}

export function EconomicEventsCard({ calendar }: { calendar: EconomicCalendar | null }) {
  const emptyMessage =
    calendar?.status === "not_configured"
      ? "Economic calendar is not configured. Add a Trading Economics API key " +
        "to enable live events."
      : calendar?.status === "unavailable"
        ? "Economic events are temporarily unavailable."
        : "No India economic events are scheduled in the next 14 days.";
  return (
    <Card>
      <CardHeader className="border-b">
        <CardTitle>Economic Events</CardTitle>
        <p className="text-xs text-muted-foreground">
          Upcoming India releases · {calendar?.provider ?? "Trading Economics"}
        </p>
      </CardHeader>
      <CardContent>
        {!calendar || calendar.events.length === 0 ? (
          <p className="text-sm text-muted-foreground">{emptyMessage}</p>
        ) : (
          <ul
            aria-label="Upcoming economic events"
            className="flex gap-4 overflow-x-auto pb-2"
          >
            {calendar.events.map((event) => (
              <EventCard key={event.event_id} event={event} />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
