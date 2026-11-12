import { RefreshCw, Sparkles } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import novidadesLocais from '../novidades.json'
const VERSAO = __APP_VERSAO__

type Novidade = { versao: string; data: string; itens: string[] }

const VISTA = 'pm_versao_vista'
const INTERVALO_MS = 5 * 60_000

/** compara "1.22.0" com "1.21.3": >0 se a primeira for mais nova */
function comparar(a: string, b: string) {
  const x = a.split('.').map(Number)
  const y = b.split('.').map(Number)
  for (let i = 0; i < 3; i++) if ((x[i] || 0) !== (y[i] || 0)) return (x[i] || 0) - (y[i] || 0)
  return 0
}

const dataBR = (d: string) => d.split('-').reverse().join('/')

/**
 * Tela cheia de versão:
 * - "disponível": o servidor tem versão mais nova que a aberta (confere ao abrir, a cada 5 min e ao voltar ao app) → botão Atualizar aplicativo;
 * - "atualizado": acabou de abrir uma versão nova pela primeira vez → mostra o que mudou uma vez.
 */
export default function NovaVersao() {
  const [tela, setTela] = useState<{ modo: 'disponivel' | 'atualizado'; versao: string; novidades: Novidade[] } | null>(() => {
    try {
      // sem registro (versões antigas do app não guardavam): mostra só as novidades desta versão
      const vista = localStorage.getItem(VISTA)
      if (!vista) {
        const desta = (novidadesLocais as Novidade[]).filter((n) => n.versao === VERSAO)
        return desta.length ? { modo: 'atualizado', versao: VERSAO, novidades: desta } : null
      }
      if (comparar(VERSAO, vista) > 0) {
        const novidades = (novidadesLocais as Novidade[]).filter((n) => comparar(n.versao, vista) > 0 && comparar(n.versao, VERSAO) <= 0)
        return novidades.length ? { modo: 'atualizado', versao: VERSAO, novidades } : null
      }
    } catch {
      /* sem armazenamento: segue sem a tela */
    }
    return null
  })
  const [atualizando, setAtualizando] = useState(false)
  const dispensada = useRef('') // "Agora não": não insiste com a mesma versão até reabrir o app

  useEffect(() => {
    if (tela?.modo === 'atualizado') return
    try {
      localStorage.setItem(VISTA, VERSAO)
    } catch {
      /* ignora */
    }
  }, [tela])

  useEffect(() => {
    if (import.meta.env.DEV) return
    let parado = false
    async function conferir() {
      try {
        const r = await fetch(`/version.json?t=${Date.now()}`, { cache: 'no-store' })
        if (!r.ok) return
        const j = (await r.json()) as { versao: string; novidades: Novidade[] }
        if (parado || comparar(j.versao, VERSAO) <= 0 || dispensada.current === j.versao) return
        const novidades = (j.novidades || []).filter((n) => comparar(n.versao, VERSAO) > 0)
        setTela((t) => (t?.modo === 'disponivel' && t.versao === j.versao ? t : { modo: 'disponivel', versao: j.versao, novidades }))
      } catch {
        /* sem internet: tenta depois */
      }
    }
    void conferir()
    const timer = setInterval(conferir, INTERVALO_MS)
    const aoVoltar = () => document.visibilityState === 'visible' && void conferir()
    document.addEventListener('visibilitychange', aoVoltar)
    return () => {
      parado = true
      clearInterval(timer)
      document.removeEventListener('visibilitychange', aoVoltar)
    }
  }, [])

  async function atualizar() {
    setAtualizando(true)
    try {
      localStorage.setItem(VISTA, tela?.versao ?? VERSAO) // já viu o que mudou: não repete depois de atualizar
      const reg = await navigator.serviceWorker?.getRegistration()
      await reg?.update()
    } catch {
      /* recarrega mesmo assim */
    }
    const url = new URL(location.href)
    url.searchParams.set('v', tela?.versao ?? String(Date.now()))
    location.replace(url.toString())
  }

  function fechar() {
    try {
      localStorage.setItem(VISTA, VERSAO)
    } catch {
      /* ignora */
    }
    setTela(null)
  }

  if (!tela) return null
  const disponivel = tela.modo === 'disponivel'

  return (
    <div className="fixed inset-0 z-[100] bg-[#0a0a0a] overflow-y-auto" role="dialog" aria-modal="true" aria-labelledby="nova-versao-titulo">
      <div className="aurora" />
      <div className="relative z-10 min-h-full max-w-xl mx-auto flex flex-col px-6 pt-[max(env(safe-area-inset-top),40px)] pb-[max(env(safe-area-inset-bottom),24px)]">
        <div className="w-16 h-16 rounded-3xl bg-lime-300 text-black grid place-items-center">
          <Sparkles className="w-8 h-8" />
        </div>
        <p className="mt-6 text-sm text-white/60">{disponivel ? 'Versão nova disponível' : 'Aplicativo atualizado'}</p>
        <h1 id="nova-versao-titulo" className="text-4xl font-medium tracking-tight mt-1">
          Versão {tela.versao}
        </h1>
        <p className="mt-2 text-white/60">{disponivel ? 'Atualize para usar as novidades:' : 'O que mudou:'}</p>

        <div className="mt-6 space-y-4 flex-1">
          {tela.novidades.length === 0 && <p className="text-white/70">Melhorias e correções.</p>}
          {tela.novidades.map((n) => (
            <section key={n.versao} className="rounded-3xl bg-[#161616] border border-white/[0.06] p-5">
              <p className="text-xs text-white/50">
                Versão {n.versao} · {dataBR(n.data)}
              </p>
              <ul className="mt-3 space-y-2.5">
                {n.itens.map((t, i) => (
                  <li key={i} className="flex gap-3 text-[15px] text-white/90">
                    <span className="mt-2 w-1.5 h-1.5 rounded-full bg-lime-300 shrink-0" />
                    <span>{t}</span>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>

        <div className="mt-8 space-y-2">
          {disponivel ? (
            <>
              <button onClick={atualizar} disabled={atualizando} className="w-full flex items-center justify-center gap-2 rounded-full bg-lime-300 text-black font-medium py-4 text-base hover:bg-lime-200 disabled:opacity-60">
                <RefreshCw className={`w-5 h-5 ${atualizando ? 'animate-spin' : ''}`} /> {atualizando ? 'Atualizando…' : 'Atualizar aplicativo'}
              </button>
              <button onClick={() => ((dispensada.current = tela.versao), setTela(null))} className="w-full rounded-full py-3 text-sm text-white/60 hover:text-white">
                Agora não
              </button>
            </>
          ) : (
            <button onClick={fechar} className="w-full rounded-full bg-lime-300 text-black font-medium py-4 text-base hover:bg-lime-200">
              Continuar
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
