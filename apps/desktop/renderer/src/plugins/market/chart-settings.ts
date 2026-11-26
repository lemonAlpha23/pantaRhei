export const chartRanges = [
  { label: '1月', count: 21 }, { label: '3月', count: 63 }, { label: '6月', count: 126 },
  { label: '1年', count: 252 }, { label: '全部', count: Infinity },
]

export interface ChartSettings {
  range: number
  mode: 'candle' | 'line'
  ma5: boolean
  ma20: boolean
  volume: boolean
}

const rangeKey = (count: number) => count === Infinity ? 'all' : String(count)

export const chartSnapshot = (settings: ChartSettings) => ({
  range: rangeKey(settings.range), mode: settings.mode,
  ma5: settings.ma5 ? '1' : '0', ma20: settings.ma20 ? '1' : '0', volume: settings.volume ? '1' : '0',
})

export const restoreChartSettings = (snapshot: Readonly<Record<string, string>>): ChartSettings => ({
  range: chartRanges.find(item => rangeKey(item.count) === snapshot.range)?.count ?? 63,
  mode: snapshot.mode === 'line' ? 'line' : 'candle',
  ma5: snapshot.ma5 !== '0', ma20: snapshot.ma20 !== '0', volume: snapshot.volume !== '0',
})
