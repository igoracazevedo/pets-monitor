import { execSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, type Plugin } from 'vite'

const pacote = JSON.parse(readFileSync(new URL('./package.json', import.meta.url), 'utf8')) as { version: string }
const commit = (process.env.VERCEL_GIT_COMMIT_SHA ?? (() => { try { return execSync('git rev-parse HEAD').toString() } catch { return 'local' } })()).trim().slice(0, 7)

// version.json: o app consulta este arquivo para saber que saiu versão nova e o que mudou
function versionJson(): Plugin {
  return {
    name: 'version-json',
    generateBundle() {
      const novidades = JSON.parse(readFileSync(new URL('./src/novidades.json', import.meta.url), 'utf8'))
      this.emitFile({ type: 'asset', fileName: 'version.json', source: JSON.stringify({ versao: pacote.version, commit, novidades: novidades.slice(0, 15) }) })
    },
  }
}

export default defineConfig({
  plugins: [react(), tailwindcss(), versionJson()],
  define: {
    __APP_VERSAO__: JSON.stringify(pacote.version),
    __APP_COMMIT__: JSON.stringify(commit),
    __APP_COMPILACAO__: JSON.stringify(new Date().toISOString()), // hora em que o Vercel compilou
  },
})
