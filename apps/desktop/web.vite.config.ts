import { defineConfig, mergeConfig } from 'vite'
import { homedir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { renderer } from './electron.vite.config'
import { createBackend } from './main/backend'

export default defineConfig(async () => {
  const backend = createBackend({
    projectDir: fileURLToPath(new URL('../backend/', import.meta.url)),
    dataDir: process.env.PANTARHEI_DATA_DIR || join(homedir(), '.pantarhei', 'preview'),
  })
  const { origin, token } = await backend.connect()
  return mergeConfig(renderer, defineConfig({
    server: { proxy: { '/api': { target: origin, headers: { Authorization: 'Bearer ' + token } } } },
    plugins: [{
      name: 'local-market-service',
      configureServer: server => { server.httpServer?.once('close', backend.stop) },
      closeBundle: backend.stop,
    }],
  }))
})
