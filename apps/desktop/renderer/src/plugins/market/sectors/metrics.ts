import type { Instrument } from '../api'

export interface SectorMetric {
  id: string
  count: number
  valid: number
  changePercent: number | null
  up: number
  down: number
  flat: number
  unknown: number
  members: Instrument[]
}

const isQuoteDate = (date: string) => {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return false
  const parsed = Date.parse(date)
  return Number.isFinite(parsed) && new Date(parsed).toISOString().slice(0, 10) === date
}

export const sectorDates = (stocks: readonly Instrument[]): string[] =>
  [...new Set(stocks.map(stock => stock.asOf))].filter(isQuoteDate).sort().reverse()

const hasChange = (value: number | null): value is number => value !== null && Number.isFinite(value)

const compareMembers = (a: Instrument, b: Instrument) => {
  const left = hasChange(a.changePercent) ? a.changePercent : -Infinity
  const right = hasChange(b.changePercent) ? b.changePercent : -Infinity
  return left === right ? a.symbol.localeCompare(b.symbol) : right - left
}

const summarize = (id: string, members: Instrument[]): SectorMetric => {
  let up = 0, down = 0, flat = 0, total = 0
  for (const { changePercent } of members) {
    if (!hasChange(changePercent)) continue
    total += changePercent
    if (changePercent > 0) up++
    else if (changePercent < 0) down++
    else flat++
  }
  const count = members.length
  const valid = up + down + flat
  return {
    id, count, valid, up, down, flat, unknown: count - valid,
    changePercent: valid ? total / valid : null,
    members: members.sort(compareMembers),
  }
}

export const sectorMetrics = (stocks: readonly Instrument[], date: string): SectorMetric[] => {
  if (!isQuoteDate(date)) return []
  const groups = new Map<string, Instrument[]>()
  for (const stock of stocks) {
    if (stock.asOf !== date) continue
    const id = stock.sector.trim() || '未分类'
    const members = groups.get(id)
    if (members) members.push(stock)
    else groups.set(id, [stock])
  }
  return [...groups].map(([id, members]) => summarize(id, members))
    .sort((a, b) => b.count - a.count || a.id.localeCompare(b.id, 'zh-CN'))
}
