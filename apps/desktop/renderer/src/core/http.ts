import { jsonOptions, readJson, type JsonRequest } from '../../../shared/http'

export const fetchTransport: JsonRequest = async (path, method = 'GET', body) =>
  readJson(await fetch(path, jsonOptions(method, body)))

export const errorText = (error: unknown, fallback: string) => {
  if (!(error instanceof Error)) return fallback
  const message = error.message.replace(/^.*?Error invoking remote method .*?: Error: /, '').trim()
  return message && message.length < 240 && !/failed to fetch|ECONNREFUSED|Load failed/i.test(message)
    ? message : fallback
}
