import { useEffect, useState } from 'react'
import type { Session } from '@supabase/supabase-js'
import { Camera as CamIcon, Dog, History, PawPrint, Settings } from 'lucide-react'
import { supabase } from './lib/supabase'
import Inicio from './components/Inicio'
import Historico from './components/Historico'
import Cameras from './components/Cameras'
import Ajustes from './components/Ajustes'
import Pets from './components/Pets'

const abas = [
  { id: 'inicio', nome: 'Início', Icone: PawPrint },
  { id: 'historico', nome: 'Histórico', Icone: History },
  { id: 'cameras', nome: 'Câmeras', Icone: CamIcon },
  { id: 'pets', nome: 'Pets', Icone: Dog },
  { id: 'ajustes', nome: 'Ajustes', Icone: Settings },
] as const
type Aba = (typeof abas)[number]['id']

export default function App() {
  const [sessao, setSessao] = useState<Session | null | undefined>(undefined)
  const [acesso, setAcesso] = useState<{ membro: boolean; admin: boolean } | null>(null)
  const [aba, setAba] = useState<Aba>('inicio')

  useEffect(() => {
    void supabase.auth.getSession().then(({ data }) => setSessao(data.session))
    const { data } = supabase.auth.onAuthStateChange((_e, s) => setSessao(s))
    return () => data.subscription.unsubscribe()
  }, [])

  useEffect(() => {
    if (!sessao) return setAcesso(null)
    void Promise.all([supabase.rpc('pm_is_membro'), supabase.rpc('pm_is_admin')]).then(([m, a]) => setAcesso({ membro: m.data === true, admin: a.data === true }))
  }, [sessao])

  if (sessao === undefined) return <p className="p-10 text-center text-slate-500">Carregando…</p>

  if (!sessao)
    return (
      <main className="mx-auto flex min-h-screen max-w-sm flex-col items-center justify-center gap-5 p-6 text-center">
        <span className="flex h-20 w-20 items-center justify-center rounded-3xl bg-cyan-700 text-white">
          <PawPrint size={38} />
        </span>
        <h1 className="text-2xl font-extrabold text-slate-900">Pets Monitor</h1>
        <p className="text-sm text-slate-600">Onde estão seus pets, segundo as câmeras de casa.</p>
        <button className="pilula w-full justify-center" onClick={() => void supabase.auth.signInWithOAuth({ provider: 'google', options: { redirectTo: window.location.origin } })}>
          Entrar com Google
        </button>
      </main>
    )

  if (!acesso) return <p className="p-10 text-center text-slate-500">Verificando acesso…</p>

  if (!acesso.membro)
    return (
      <main className="mx-auto max-w-sm space-y-4 p-8 text-center">
        <p className="text-slate-700">O e-mail {sessao.user.email} não tem acesso. Peça ao administrador para liberar.</p>
        <button className="pilula" onClick={() => void supabase.auth.signOut()}>
          Sair
        </button>
      </main>
    )

  return (
    <div className="mx-auto min-h-screen max-w-3xl pb-24">
      <header className="sticky top-0 z-10 flex items-center justify-between bg-[#0e7490] px-4 py-3 text-white">
        <h1 className="flex items-center gap-2 font-extrabold">
          <PawPrint size={20} /> Pets Monitor
        </h1>
        <button className="text-[12px] opacity-80" onClick={() => void supabase.auth.signOut()}>
          Sair
        </button>
      </header>
      <main className="p-4">
        {aba === 'inicio' && <Inicio />}
        {aba === 'historico' && <Historico />}
        {aba === 'cameras' && <Cameras />}
        {aba === 'pets' && <Pets admin={acesso.admin} />}
        {aba === 'ajustes' && <Ajustes admin={acesso.admin} />}
      </main>
      <nav className="vidro fixed inset-x-3 bottom-3 mx-auto flex max-w-md justify-around p-1.5">
        {abas.map(({ id, nome, Icone }) => (
          <button key={id} onClick={() => setAba(id)} className={`flex flex-1 flex-col items-center gap-0.5 rounded-2xl py-1.5 text-[11px] font-semibold ${aba === id ? 'bg-cyan-700/10 text-cyan-800' : 'text-slate-500'}`}>
            <Icone size={20} />
            {nome}
          </button>
        ))}
      </nav>
    </div>
  )
}
