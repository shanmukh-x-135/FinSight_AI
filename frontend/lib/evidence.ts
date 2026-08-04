import type {
  Breadth,
  HistoryStatistics,
  Quote,
  Recommendation,
  ReportSections,
} from "@/lib/api";
import { money, pct, ratioPct } from "@/lib/utils";

interface MarketFacts {
  breadth?: Breadth;
  gainers?: Quote[];
  losers?: Quote[];
}

interface PortfolioFacts {
  total_value?: number | null;
  total_return_percent?: number | null;
  health_score?: number | null;
  risk_level?: string;
  diversification_score?: number | null;
  number_of_holdings?: number;
}

function moverEvidence(label: string, quote: Quote | undefined): string | null {
  if (!quote) return null;
  return `${label}: ${quote.symbol} at ${pct(quote.change_percent)}`;
}

/** Deterministic market facts used to generate a market narrative. */
export function marketNarrativeEvidence(market: MarketFacts): string[] {
  return [
    market.breadth
      ? `Breadth: ${market.breadth.advancers} advancers, ${market.breadth.decliners} decliners, and ${market.breadth.unchanged} unchanged across ${market.breadth.total} tracked stocks`
      : null,
    market.breadth?.advance_decline_ratio == null
      ? null
      : `Advance/decline ratio: ${market.breadth.advance_decline_ratio.toFixed(2)}`,
    moverEvidence("Top gainer", market.gainers?.[0]),
    moverEvidence("Top decliner", market.losers?.[0]),
  ].filter((item): item is string => item !== null);
}

/** Deterministic portfolio facts used to generate a portfolio narrative. */
export function portfolioNarrativeEvidence(portfolio: PortfolioFacts): string[] {
  return [
    portfolio.total_value == null ? null : `Portfolio value: ${money(portfolio.total_value)}`,
    portfolio.total_return_percent == null
      ? null
      : `Total return: ${pct(portfolio.total_return_percent)}`,
    portfolio.health_score == null ? null : `Health score: ${portfolio.health_score}/100`,
    portfolio.risk_level ? `Risk level: ${portfolio.risk_level}` : null,
    portfolio.diversification_score == null
      ? null
      : `Diversification score: ${portfolio.diversification_score}/100`,
    portfolio.number_of_holdings == null
      ? null
      : `Holdings analysed: ${portfolio.number_of_holdings}`,
  ].filter((item): item is string => item !== null);
}

/** Deterministic historical outcomes used to generate a historical narrative. */
export function historicalNarrativeEvidence(statistics: HistoryStatistics): string[] {
  return [
    `Comparable sessions with outcomes: ${statistics.sample_size}`,
    statistics.bullish_probability == null
      ? null
      : `Closed higher next day: ${ratioPct(statistics.bullish_probability, 0, false)}`,
    statistics.avg_next_day_return == null
      ? null
      : `Average next-day return: ${ratioPct(statistics.avg_next_day_return)}`,
    statistics.median_next_day_return == null
      ? null
      : `Median next-day return: ${ratioPct(statistics.median_next_day_return)}`,
  ].filter((item): item is string => item !== null);
}

/** Source facts for the report-level synthesis, kept concise for disclosure UI. */
export function executiveNarrativeEvidence(sections: ReportSections): string[] {
  const evidence = [
    ...(sections.market_summary
      ? marketNarrativeEvidence(sections.market_summary).slice(0, 2)
      : []),
    ...(sections.portfolio_summary
      ? portfolioNarrativeEvidence(sections.portfolio_summary).slice(0, 2)
      : []),
    ...(sections.historical_summary?.statistics
      ? historicalNarrativeEvidence(sections.historical_summary.statistics).slice(0, 2)
      : []),
  ];

  const watchlist = (sections.recommendations ?? [])
    .filter((recommendation: Recommendation) => recommendation.action === "watch")
    .map((recommendation) => `${recommendation.symbol} (${recommendation.confidence}% confidence)`);
  if (watchlist.length > 0) evidence.push(`Watch-rated: ${watchlist.join(", ")}`);
  return evidence;
}
