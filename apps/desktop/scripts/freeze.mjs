import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const backend = fileURLToPath(new URL('../../backend/', import.meta.url))
const output = fileURLToPath(new URL('../dist/service/', import.meta.url))
const entry = fileURLToPath(new URL('./backend_entry.py', import.meta.url))
const run = spawnSync('uv', [
  'run', '--locked', '--group', 'package', 'pyinstaller', '--noconfirm', '--onedir',
  '--name', 'market-service', '--paths', backend, '--collect-data', 'app.plugins',
  ...(process.platform === 'darwin' ? ['--copy-metadata', 'keyring', '--hidden-import', 'keyring.backends.macOS.api'] : []),
  '--collect-submodules', 'uvicorn', '--distpath', output,
  '--workpath', path.join(output, 'work'), '--specpath', path.join(output, 'spec'), entry,
], { cwd: backend, stdio: 'inherit', windowsHide: true })
if (run.error) throw run.error
process.exitCode = run.status ?? 1
