export const number = (value: number | null | undefined, digits = 2) =>
  value == null || !Number.isFinite(value) ? '—' : value.toLocaleString('zh-CN', {
    minimumFractionDigits: digits, maximumFractionDigits: digits,
  })

export const signed = (value: number | null | undefined) =>
  value == null ? '—' : (value > 0 ? '+' : '') + number(value)

export const percent = (value: number | null | undefined) => value == null ? '—' : signed(value) + '%'

export const direction = (value: number | null | undefined) =>
  value == null || value === 0 ? 'flat' : value > 0 ? 'up' : 'down'

export const volume = (value: number | undefined) => {
  if (value === undefined) return '—'
  if (value >= 100000000) return number(value / 100000000) + ' 亿股'
  if (value >= 10000) return number(value / 10000) + ' 万股'
  return number(value, 0) + ' 股'
}

export const exchangeName = (code: string) =>
  ({ SSE: '上海证券交易所', SZSE: '深圳证券交易所' }[code] ?? code)

export const exchangeTag = (code: string) =>
  ({ SSE: '沪市', SZSE: '深市' }[code] ?? code)
