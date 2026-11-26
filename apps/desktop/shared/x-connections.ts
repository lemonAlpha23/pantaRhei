export type XConnection = 'x' | 'webhook'
type Source = 'saved' | 'environment' | 'none'

interface ConfiguredField {
  configured: boolean
  source: Source
}

export interface XSettings {
  revision: number
  xToken: ConfiguredField
  webhookUrl: ConfiguredField & { host: string | null }
  webhookToken: ConfiguredField
  storageAvailable: boolean
}

export type XSettingsPatch = Partial<Record<'xToken' | 'webhookUrl' | 'webhookToken', string | null>>

export interface XTestResult {
  ok: boolean
  message: string
  testedAt: string
}

export type XDeliveryStatus = 'pending' | 'sent' | 'failed'

export interface XDelivery {
  id: string
  handle: string
  status: XDeliveryStatus
  attempts: number
  createdAt: string | null
  lastAttemptAt: string | null
  nextAttemptAt: string | null
  httpStatus: number | null
  error: string | null
  retryable: boolean
  retryBlockedReason: string | null
}

export interface XDeliveryPage {
  items: XDelivery[]
  nextCursor: number | null
}

export interface XDeliveryAttempt {
  number: number
  at: string | null
  status: 'sent' | 'failed' | 'sending' | 'unknown'
  httpStatus: number | null
  error: string | null
}
