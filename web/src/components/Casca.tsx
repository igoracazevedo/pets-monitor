import { useEffect, useRef, useState } from 'react'
import type { Session } from '@supabase/supabase-js'
import { HelpCircle, LogOut, X } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { supabase } from '../lib/supabase'

export type AbaDef = { id: string; nome: string; Icone: LucideIcon; ajuda: string[] }

const hora = new Date(__APP_COMPILACAO__).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' })

function Avatar({ sessao, grande }: { sessao: Session; grande?: boolean }) {
  const tam = grande ? 'h-12 w-12' : 'h-12 w-12'
  const meta = (sessao.user.user_metadata ?? {}) as { avatar_url?: string; picture?: string; full_name?: string; name?: string }
  const url = meta.avatar_url ?? meta.picture
  const nome = meta.full_name ?? meta.name ?? sessao.user.email ?? 'U'
  if (url) return <img src={url} alt="" referrerPolicy="no-referrer" className={`${tam} rounded-full ring-2 ring-white/20 object-cover`} />
  const iniciais = nome.split(/\s+/).slice(0, 2).map((p) => p[0]?.toUpperCase()).join('')
  return <span className={`flex ${tam} items-center justify-center rounded-full ring-2 ring-white/20 bg-white/10 text-[14px] font-medium text-white`}>{iniciais}</span>
}

/** Moldura do app no padrão IAZ: topo colorido com avatar/menu, pílula central e ajuda; folha curvada com atalhos em squircles. */
export function Casca({ sessao, abas, abasTopo = [], aba, onAba, children }: { sessao: Session; abas: AbaDef[]; abasTopo?: AbaDef[]; aba: string; onAba: (id: string) => void; children: React.ReactNode }) {
  const [menu, setMenu] = useState(false)
  const [ajuda, setAjuda] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const atual = [...abas, ...abasTopo].find((a) => a.id === aba)
  const nome = ((sessao.user.user_metadata ?? {}) as { full_name?: string; name?: string }).full_name ?? sessao.user.email ?? 'Usuário'

  useEffect(() => {
    if (!menu) return
    const fora = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setMenu(false)
    document.addEventListener('mousedown', fora)
    return () => document.removeEventListener('mousedown', fora)
  }, [menu])
  useEffect(() => setMenu(false), [aba])

  return (
    <div className="relative min-h-dvh overflow-x-hidden">
      <div className="aurora" />
      <div className="relative z-10 mx-auto max-w-5xl px-4 pb-32 pt-[max(env(safe-area-inset-top),16px)]">
        <header className="flex items-center justify-between py-2">
          <div className="relative" ref={ref}>
            <button onClick={() => setMenu((m) => !m)} className="flex items-center gap-2 rounded-full" aria-label="Menu do usuário">
              <Avatar sessao={sessao} />
            </button>
            {menu && (
              <div className="absolute left-0 top-14 z-50 w-64 overflow-hidden rounded-3xl border border-white/10 bg-[#1c1c1c] text-white shadow-2xl shadow-black/60">
                <div className="flex items-center gap-3 border-b border-white/10 px-4 py-3">
                  <Avatar sessao={sessao} grande />
                  <div className="min-w-0">
                    <p className="truncate font-medium">{nome}</p>
                    <p className="truncate text-[12px] text-white/60">{sessao.user.email}</p>
                  </div>
                </div>
                <button onClick={() => void supabase.auth.signOut()} className="flex w-full items-center gap-3 px-4 py-2.5 text-left hover:bg-white/10">
                  <LogOut size={16} strokeWidth={1.9} /> Sair
                </button>
                <div className="border-t border-white/10 px-4 py-2 text-[11px] leading-relaxed text-white/50">
                  <p>Pets Monitor IAZ · versão {__APP_VERSAO__}</p>
                  <p>Compilação {__APP_COMMIT__} · {hora}</p>
                </div>
              </div>
            )}
          </div>

          <div className="flex items-center gap-2">
            {abasTopo.map(({ id, nome: rotulo, Icone }) => (
              <button
                key={id}
                onClick={() => onAba(id)}
                aria-label={rotulo}
                title={rotulo}
                className={`grid h-11 w-11 place-items-center rounded-full border border-white/10 transition-colors ${id === aba ? 'bg-lime-300 text-black' : 'bg-[#1c1c1c]/90 text-white/80 hover:text-white'}`}
              >
                <Icone size={20} strokeWidth={1.8} />
              </button>
            ))}
            <button onClick={() => setAjuda(true)} aria-label="Ajuda" className="grid h-11 w-11 place-items-center rounded-full border border-white/10 bg-[#1c1c1c]/90 text-white/80 transition-colors hover:text-white">
              <HelpCircle size={20} strokeWidth={1.8} />
            </button>
          </div>
        </header>

        <main className="min-w-0 pt-2">{children}</main>
      </div>

      {/* Barra inferior flutuante: abas em pílula */}
      <nav className="pointer-events-none fixed inset-x-0 bottom-0 z-20 px-4 pb-[max(env(safe-area-inset-bottom),14px)]">
        <div className="pointer-events-auto mx-auto flex max-w-xl items-center rounded-full border border-white/10 bg-[#1c1c1c]/90 p-1.5 shadow-2xl shadow-black/60 backdrop-blur-xl">
          {abas.map(({ id, nome: rotulo, Icone }) => (
            <button
              key={id}
              onClick={() => onAba(id)}
              aria-label={rotulo}
              title={rotulo}
              className={`grid h-12 flex-1 place-items-center rounded-full transition-colors ${id === aba ? 'bg-black text-lime-300' : 'text-white/70 hover:text-white'}`}
            >
              <Icone className="h-[22px] w-[22px]" strokeWidth={1.8} />
            </button>
          ))}
        </div>
      </nav>

      {ajuda && atual && (
        <div className="fixed inset-0 z-[60] flex items-end justify-center bg-black/50 sm:items-center sm:p-4" onClick={() => setAjuda(false)}>
          <div className="w-full max-w-md rounded-t-3xl border border-white/10 bg-[#1c1c1c] p-5 sm:rounded-3xl" onClick={(e) => e.stopPropagation()}>
            <div className="mb-3 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <HelpCircle size={18} strokeWidth={1.9} className="text-lime-300" />
                <h2 className="font-medium tracking-tight text-white">Como usar esta tela · {atual.nome}</h2>
              </div>
              <button onClick={() => setAjuda(false)} className="rounded-full p-1.5 text-white/60 hover:bg-white/10" aria-label="Fechar">
                <X size={18} strokeWidth={1.9} />
              </button>
            </div>
            <ol className="space-y-2">
              {atual.ajuda.map((s, i) => (
                <li key={i} className="flex gap-3">
                  <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-lime-300/10 text-[11px] font-medium text-lime-300">{i + 1}</span>
                  <span className="text-white/80">{s}</span>
                </li>
              ))}
            </ol>
          </div>
        </div>
      )}
    </div>
  )
}
