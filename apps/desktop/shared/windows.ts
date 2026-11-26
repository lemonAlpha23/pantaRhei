export interface WindowTarget {
  page: string
  state?: Record<string, string>
}

export interface WindowsApi {
  openPage: (target: WindowTarget) => Promise<void>
}

const validId = (value: unknown): value is string =>
  typeof value === 'string' && value.length > 0 && value.length <= 64 && /^[a-z]/i.test(value) && !/[^a-z0-9_-]/i.test(value)

const isRecord = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === 'object' &&
  (Object.getPrototypeOf(value) === Object.prototype || Object.getPrototypeOf(value) === null)

const validateTarget = (value: unknown): WindowTarget => {
  if (!isRecord(value) || !validId(value.page)) throw new Error('无效的工作台页面')
  if (value.state === undefined) return { page: value.page }
  if (!isRecord(value.state)) throw new Error('无效的页面状态')
  const entries = Object.entries(value.state)
  if (entries.length > 16) throw new Error('无效的页面状态')
  const state: Record<string, string> = {}
  for (const [key, item] of entries) {
    if (!validId(key) || key === 'constructor' || key === 'prototype' || typeof item !== 'string' || item.length > 256) {
      throw new Error('无效的页面状态')
    }
    state[key] = item
  }
  return { page: value.page, state }
}

export const encodeWindowTarget = (target: WindowTarget): string =>
  '#window=' + encodeURIComponent(JSON.stringify(validateTarget(target)))

export const readWindowTarget = (hash: string): WindowTarget | undefined => {
  if (!hash.startsWith('#window=') || hash.length > 65536) return
  try {
    return validateTarget(JSON.parse(decodeURIComponent(hash.slice('#window='.length))))
  } catch {
    return undefined
  }
}
