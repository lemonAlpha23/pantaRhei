import { defineConfig } from 'electron-vite'
import type { Plugin, UserConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { Script } from 'node:vm'

const desktopDir = fileURLToPath(new URL('.', import.meta.url))

// electron-vite also builds the main process before launching in development.
// Parse the emitted CommonJS here so a broken entry never reaches Electron.
const checkCommonJs = (): Plugin => ({
  name: 'check-electron-commonjs',
  generateBundle: (_options, files) => {
    for (const file of Object.values(files)) {
      if (file.type === 'chunk') new Script(file.code, { filename: file.fileName })
    }
  },
})

export const renderer: UserConfig = {
  root: resolve(desktopDir, 'renderer'),
  plugins: [vue()],
  base: './',
  server: { host: '127.0.0.1' },
  build: {
    minify: true,
    license: { fileName: 'THIRD-PARTY-LICENSES.txt' },
    outDir: resolve(desktopDir, 'dist/renderer'),
    emptyOutDir: true,
    rollupOptions: { input: resolve(desktopDir, 'renderer/index.html') },
  },
}

export default defineConfig({
  main: {
    oxc: { decorator: { legacy: true } },
    plugins: [checkCommonJs()],
    build: {
      outDir: 'dist/main',
      lib: { entry: resolve(desktopDir, 'main/index.ts'), formats: ['cjs'] },
      rollupOptions: { output: { entryFileNames: 'index.cjs' } },
    },
  },
  preload: {
    plugins: [checkCommonJs()],
    build: {
      outDir: 'dist/preload',
      lib: { entry: resolve(desktopDir, 'preload/index.ts'), formats: ['cjs'] },
      rollupOptions: { output: { entryFileNames: 'index.cjs' } },
    },
  },
  renderer,
})
