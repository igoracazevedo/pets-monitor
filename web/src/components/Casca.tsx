import { useEffect, useRef, useState } from 'react'
import type { Session } from '@supabase/supabase-js'
import { HelpCircle, LogOut, X } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { supabase } from '../lib/supabase'

export type AbaDef = { id: string; nome: string; Icone: LucideIcon; ajuda: string[] }

const COR = '#0e7490'
const COR_MENU = '#074b5e'
const hora = new Date(__APP_COMPILACAO__).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' })

function Avatar({ sessao, grande }: { sessao: Session; grande?: boolean }) {
  const tam = grande ? 'h-12 w-12' : 'h-9 w-9'
  const meta = (sessao.user.user_metadata ?? {}) as { avatar_url?: string; picture?: string; full_name?: string; name?: string }
  const url = meta.avatar_url ?? meta.picture
  const nome = meta.full_name ?? meta.name ?? sessao.user.email ?? 'U'
  if (url) return <img src={url} alt="" referrerPolicy="no-referrer" className={`${tam} rounded-full border-2 border-white/20 object-cover`} />
  const iniciais = nome.split(/\s+/).slice(0, 2).map((p) => p[0]?.toUpperCase()).join('')
  return <span className={`flex ${tam} items-center justify-center rounded-full border-2 border-white/20 bg-[#0b3a49] text-[12px] font-bold text-white`}>{iniciais}</span>
}

/** Moldura do app no padrão IAZ: topo colorido com avatar/menu, pílula central e ajuda; folha curvada com atalhos em squircles. */
export function Casca({ sessao, abas, aba, onAba, children }: { sessao: Session; abas: AbaDef[]; aba: string; onAba: (id: string) => void; children: React.ReactNode }) {
  const [menu, setMenu] = useState(false)
  const [ajuda, setAjuda] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const atual = abas.find((a) => a.id === aba)
  const nome = ((sessao.user.user_metadata ?? {}) as { full_name?: string; name?: string }).full_name ?? sessao.user.email ?? 'Usuário'

  useEffect(() => {
    if (!menu) return
    const fora = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setMenu(false)
    document.addEventListener('mousedown', fora)
    return () => document.removeEventListener('mousedown', fora)
  }, [menu])
  useEffect(() => setMenu(false), [aba])

  return (
    <div className="min-h-dvh">
      <header className="pb-7 text-white" style={{ background: COR }}>
        <div className="relative mx-auto flex max-w-5xl items-center justify-between px-4 pt-3">
          <div className="relative" ref={ref}>
            <button onClick={() => setMenu((m) => !m)} className="flex items-center gap-2 rounded-full p-0.5 transition hover:bg-white/10" aria-label="Menu do usuário">
              <Avatar sessao={sessao} />
              <span className="hidden rounded-full bg-white/10 px-3 py-1 text-[12px] font-semibold sm:inline">{nome.split(' ')[0]}</span>
            </button>
            {menu && (
              <div className="absolute left-0 top-12 z-50 w-64 overflow-hidden rounded-2xl border border-white/10 text-white shadow-xl" style={{ background: COR_MENU }}>
                <div className="flex items-center gap-3 border-b border-white/10 px-4 py-3">
                  <Avatar sessao={sessao} grande />
                  <div className="min-w-0">
                    <p className="truncate font-bold">{nome}</p>
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

          <div className="flex min-w-0 flex-1 justify-center sm:pointer-events-none sm:absolute sm:inset-x-0 sm:top-1/2 sm:flex-none sm:-translate-y-1/2">
            <div className="flex min-w-0 items-center gap-2 rounded-2xl bg-white px-2.5 py-1.5 shadow-sm">
              <img src="/icon-192.png" alt="" className="h-6 w-6 shrink-0 rounded-lg" />
              <span className="truncate text-sm font-extrabold tracking-tight" style={{ color: '#06323f' }}>Pets Monitor</span>
            </div>
          </div>

          <div className="flex items-center gap-1">
            <button onClick={() => setAjuda(true)} aria-label="Ajuda" className="rounded-full p-2 transition hover:bg-white/10">
              <HelpCircle size={20} strokeWidth={1.9} />
            </button>
          </div>
        </div>
      </header>

      <main className="folha -mt-4 min-h-[calc(100dvh-4rem)] rounded-t-[26px]">
        <div className="mx-auto min-w-0 max-w-5xl px-4 pb-10 pt-5">
          <nav className="mb-5 flex justify-center gap-1 sm:gap-2">
            {abas.map(({ id, nome: rotulo, Icone }) => {
              const ativa = id === aba
              return (
                <button key={id} onClick={() => onAba(id)} className="group flex min-w-0 flex-1 flex-col items-center gap-1.5 sm:w-[68px] sm:flex-none">
                  <span
                    className={`flex h-11 w-11 items-center justify-center rounded-[16px] border transition duration-200 sm:h-[52px] sm:w-[52px] ${
                      ativa ? 'scale-105 text-white ring-2 ring-offset-2' : 'border-slate-200/80 bg-white text-slate-600 shadow-sm group-hover:text-[#0e7490]'
                    }`}
                    style={ativa ? { background: COR, borderColor: COR, boxShadow: '0 6px 16px -4px rgba(14,116,144,.45)', ['--tw-ring-color' as string]: 'rgba(14,116,144,.25)', ['--tw-ring-offset-color' as string]: '#e8f0f6' } : undefined}
                  >
                    <Icone size={20} strokeWidth={1.9} />
                  </span>
                  <span className={`line-clamp-2 text-center text-[10px] leading-tight sm:text-[11px] ${ativa ? 'font-bold text-[#0e7490]' : 'text-slate-600'}`}>{rotulo}</span>
                  <span className="h-1 w-5 rounded-full transition duration-200" style={{ background: ativa ? COR : 'transparent' }} />
                </button>
              )
            })}
          </nav>
          {children}
        </div>
      </main>

      {ajuda && atual && (
        <div className="fixed inset-0 z-[60] flex items-end justify-center bg-black/50 sm:items-center sm:p-4" onClick={() => setAjuda(false)}>
          <div className="w-full max-w-md rounded-t-3xl bg-white p-5 sm:rounded-3xl" onClick={(e) => e.stopPropagation()}>
            <div className="mb-3 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <HelpCircle size={18} strokeWidth={1.9} className="text-[#ffb800]" />
                <h2 className="font-extrabold tracking-tight text-slate-900">Como usar esta tela · {atual.nome}</h2>
              </div>
              <button onClick={() => setAjuda(false)} className="rounded-full p-1.5 text-slate-500 hover:bg-slate-100" aria-label="Fechar">
                <X size={18} strokeWidth={1.9} />
              </button>
            </div>
            <ol className="space-y-2">
              {atual.ajuda.map((s, i) => (
                <li key={i} className="flex gap-3">
                  <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[#0e7490]/10 text-[11px] font-bold text-[#0e7490]">{i + 1}</span>
                  <span className="text-slate-700">{s}</span>
                </li>
              ))}
            </ol>
          </div>
        </div>
      )}
    </div>
  )
}
