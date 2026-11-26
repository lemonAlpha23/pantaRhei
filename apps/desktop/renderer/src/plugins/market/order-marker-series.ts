import type { SeriesMarker, SeriesMarkerPrice } from 'lightweight-charts'
import type { XOrderMark } from '../../../../shared/xmonitor'

const shanghaiDate = new Intl.DateTimeFormat('sv-SE', {
  timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
})

export interface OrderDay {
  date: string
  orders: XOrderMark[]
}

export const groupOrderMarks = (orders: readonly XOrderMark[], bars: readonly { time: string }[]): OrderDay[] => {
  const days = new Map<string, XOrderMark[]>()
  const tradingDates = new Set(bars.map(bar => bar.time))
  for (const order of orders) {
    const timestamp = Date.parse(order.publishedAt)
    if (!Number.isFinite(timestamp)) continue
    const date = shanghaiDate.format(timestamp)
    if (!tradingDates.has(date)) continue
    const group = days.get(date)
    if (group) group.push(order)
    else days.set(date, [order])
  }
  return Array.from(days, ([date, orders]) => ({
    date, orders: orders.sort((a, b) => Date.parse(b.publishedAt) - Date.parse(a.publishedAt)),
  })).sort((a, b) => a.date.localeCompare(b.date))
}

export const orderSeriesMarkers = (days: OrderDay[], buyColor: string, sellColor: string): SeriesMarker<string>[] => {
  const markers: SeriesMarker<string>[] = []
  for (const { date, orders } of days) {
    const buys = orders.filter(order => order.action === 'buy').length
    const sells = orders.length - buys
    if (buys) markers.push({
      time: date, position: 'belowBar', shape: 'arrowUp', color: buyColor, text: buys > 1 ? String(buys) : undefined,
    })
    if (sells) markers.push({
      time: date, position: 'aboveBar', shape: 'arrowDown', color: sellColor, text: sells > 1 ? String(sells) : undefined,
    })
  }
  return markers
}

export const orderPriceMarkers = (day: OrderDay | undefined, adjustment: string | undefined,
  buyColor: string, sellColor: string): SeriesMarkerPrice<string>[] => {
  if (!day || adjustment !== '不复权') return []
  const buys = new Set<number>()
  const sells = new Set<number>()
  for (const order of day.orders) {
    if (order.priceInYuan !== true || order.price == null || !Number.isFinite(order.price) || order.price <= 0) continue
    const prices = order.action === 'buy' ? buys : sells
    prices.add(order.price)
  }
  // A smaller sell dot leaves a visible buy ring when both sides disclose the same price.
  return [
    ...Array.from(buys, price => ({ price, color: buyColor, size: sells.has(price) ? 1.1 : 0.75 })),
    ...Array.from(sells, price => ({ price, color: sellColor, size: buys.has(price) ? 0.6 : 0.75 })),
  ].map(point => ({ ...point, time: day.date, position: 'atPriceMiddle', shape: 'circle' }))
}
