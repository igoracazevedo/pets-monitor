import { execSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const pacote = JSON.parse(readFileSync(new URL('./package.json', import.meta.url), 'utf8')) as { version: string }
const commit = (process.env.VERCEL_GIT_COMMIT_SHA ?? (() => { try { return execSync('git rev-parse HEAD').toString() } catch { return 'local' } })()).trim().slice(0, 7)

export default defineConfig({
  plugins: [react(), tailwindcss()],
  define: {
    __APP_VERSAO__: JSON.stringify(pacote.version),
    __APP_COMMIT__: JSON.stringify(commit),
    __APP_COMPILACAO__: JSON.stringify(new Date().toISOString()), // hora em que o Vercel compilou
  },
})
