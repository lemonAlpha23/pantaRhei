type Method = 'GET' | 'POST' | 'DELETE' | 'PUT' | 'PATCH'
export type JsonRequest = <T>(path: string, method?: Method, body?: Record<string, unknown>) => Promise<T>

export const jsonOptions = (method: Method, body?: Record<string, unknown>, headers: Record<string, string> = {}): RequestInit =>
  body === undefined ? { method, headers }
    : { method, headers: { ...headers, 'Content-Type': 'application/json' }, body: JSON.stringify(body) }

export const readJson = async <T>(response: Response): Promise<T> => {
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(typeof body?.detail === 'string' ? body.detail : `请求失败（${response.status}）`)
  }
  return response.json()
}
