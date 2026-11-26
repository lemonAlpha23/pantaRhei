import type { Bar, History } from '../api'

export const comparisonRanges = [20, 60, 120, 250, 'all'] as const
export type ComparisonRange = (typeof comparisonRanges)[number]
export type ComparisonPreferences = { symbols: string[]; range: ComparisonRange }
export type ComparisonLoad = { status: 'loading' } | { status: 'error'; message: string } | { status: 'ready'; history: History }
export const maxComparisons = 4

const validateSymbols = (input: unknown[], available: string[], fallback: string[]) => {
  const valid = input.filter((symbol): symbol is string => typeof symbol === 'string' && available.includes(symbol))
  const symbols = [...new Set(valid)].slice(0, maxComparisons)
  return input.length > 0 && !symbols.length ? fallback : symbols
}

export const restoreComparison = (
  raw: string | null, available: string[], defaults: ComparisonPreferences = { symbols: available.slice(0, 2), range: 60 },
): ComparisonPreferences => {
  if (!raw) return defaults
  try {
    const saved = JSON.parse(raw)
    if (!Array.isArray(saved?.symbols)) return defaults
    const symbols = validateSymbols(saved.symbols, available, defaults.symbols)
    const range = comparisonRanges.find(option => option === saved.range) ?? defaults.range
    return { symbols, range }
  } catch {
    return defaults
  }
}

export const restoreComparisonWindow = (
  state: Readonly<Record<string, string>>, available: string[], fallback: ComparisonPreferences,
): ComparisonPreferences => ({
  symbols: state.symbols === undefined ? fallback.symbols
    : validateSymbols(state.symbols ? state.symbols.split(',') : [], available, fallback.symbols),
  range: comparisonRanges.find(option => String(option) === state.range) ?? fallback.range,
})

export const comparisonDates = (histories: History[], range: ComparisonRange) => {
  const dates = new Set<string>()
  for (const history of histories) {
    for (const bar of history.bars) dates.add(bar.time)
  }
  const sorted = [...dates].sort()
  return range === 'all' ? sorted : sorted.slice(-range)
}

export const comparisonSeries = (bars: Bar[], dates: string[]) => {
  const byDate = new Map(bars.map(bar => [bar.time, bar]))
  let missing = 0
  const points = dates.map(time => {
    const bar = byDate.get(time)
    if (bar) return bar
    missing++
    return { time }
  })
  const start = byDate.get(dates[0])
  const end = byDate.get(dates[dates.length - 1])
  const change = dates.length >= 2 && start && end && start.close > 0
    ? (end.close / start.close - 1) * 100 : null
  return { points, missing, change, start, end }
}
