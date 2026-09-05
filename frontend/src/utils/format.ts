/** Format token counts compactly while retaining enough precision for a task view. */
export function formatTokenCount(tokens: number | null | undefined): string {
  const value = Number(tokens)
  if (!Number.isFinite(value) || value <= 0) return '0'
  if (value < 1_000) return String(Math.round(value))

  const compact = value / 1_000
  const fractionDigits = compact >= 100 ? 0 : 1
  return `${compact.toFixed(fractionDigits).replace(/\.0$/, '')}k`
}
