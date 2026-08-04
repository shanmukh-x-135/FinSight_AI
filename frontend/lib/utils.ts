import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

// ----- Shared display formatters (used across the Phase 7 screens) ----------
export const money = (n: number | null | undefined) =>
  n == null ? "—" : `₹${n.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;

export const pct = (n: number | null | undefined) =>
  n == null ? "—" : `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`;

/** Format a decimal ratio (0.01 = 1%) for display as a percentage. */
export const ratioPct = (
  n: number | null | undefined,
  digits = 2,
  showPositiveSign = true,
) =>
  n == null
    ? "—"
    : `${showPositiveSign && n >= 0 ? "+" : ""}${(n * 100).toFixed(digits)}%`;

export const signClass = (n: number | null | undefined) =>
  n == null ? "" : n > 0 ? "text-green-600" : n < 0 ? "text-red-600" : "";
