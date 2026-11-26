import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process'
import { randomBytes } from 'node:crypto'
import { createInterface } from 'node:readline'
import path from 'node:path'
import { jsonOptions, readJson, type JsonRequest } from '../shared/http'

interface BackendOptions {
  resourcesPath?: string
  projectDir: string
  dataDir: string
}
interface Connection {
  origin: string
  token: string
}

// One child owns its listening socket from bind through shutdown. Its stdin is
// also the lifetime of the parent, including when Electron exits unexpectedly.
export const createBackend = ({ resourcesPath, projectDir, dataDir }: BackendOptions) => {
  const windows = process.platform === 'win32'
  let child: ChildProcessWithoutNullStreams | undefined
  let connection: Promise<Connection> | undefined

  const connect = () => {
    if (connection) return connection
    const token = randomBytes(32).toString('hex')
    const executable = resourcesPath
      ? path.join(resourcesPath, 'service', windows ? 'market-service.exe' : 'market-service')
      : path.join(projectDir, '.venv', windows ? 'Scripts/python.exe' : 'bin/python')
    const args = resourcesPath ? [] : ['-m', 'app']
    const service = spawn(executable, [...args, '--port', '0', '--watch-stdin'], {
      cwd: resourcesPath || projectDir,
      env: { ...process.env, PANTARHEI_TOKEN: token, PANTARHEI_DATA_DIR: dataDir, PYTHONUTF8: '1' },
      stdio: ['pipe', 'pipe', 'pipe'],
      windowsHide: true,
    })
    child = service
    service.stderr.on('data', chunk => process.stderr.write(chunk))
    connection = new Promise<Connection>((resolve, reject) => {
      const lines = createInterface({ input: service.stdout })
      const timeout = setTimeout(() => {
        reject(new Error('本地行情服务启动超时'))
        service.kill()
      }, 30_000)
      service.once('error', error => {
        clearTimeout(timeout)
        reject(error)
      })
      service.once('close', () => {
        clearTimeout(timeout)
        if (child === service) {
          child = undefined
          connection = undefined
        }
        reject(new Error('本地行情服务已退出'))
      })
      lines.on('line', line => {
        let ready
        try { ready = JSON.parse(line) } catch { return }
        if (Number.isInteger(ready.port) && ready.port > 0 && ready.port < 65536) {
          clearTimeout(timeout)
          resolve({ origin: 'http://127.0.0.1:' + ready.port, token })
        }
      })
    })
    return connection
  }

  const stop = () => {
    child?.stdin.end()
  }

  return { connect, stop }
}

export const createBackendRequest = (backend: ReturnType<typeof createBackend>): JsonRequest =>
  async (path, method = 'GET', body) => {
    const { origin, token } = await backend.connect()
    const response = await fetch(origin + path, {
      ...jsonOptions(method, body, { Authorization: 'Bearer ' + token }),
      redirect: 'error', signal: AbortSignal.timeout(25_000),
    })
    return readJson(response)
  }
