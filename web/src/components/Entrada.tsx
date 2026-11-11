import { useState } from 'react'
import { supabase } from '../lib/supabase'

function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true">
      <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z" />
      <path fill="#FF3D00" d="m6.3 14.7 6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z" />
      <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-7.9l-6.5 5C9.5 39.6 16.2 44 24 44z" />
      <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.5z" />
    </svg>
  )
}

/** Moldura das telas de entrada: faixa colorida com a logo e folha arredondada com o cartão (mesmo layout dos outros apps). */
export function TelaEntrada({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative grid min-h-dvh place-items-end overflow-hidden p-6 pb-16 sm:place-items-center">
      <div className="aurora" />
      <div className="relative z-10 w-full max-w-sm space-y-5">
        <img src="/icon-192.png" width={64} height={64} alt="Pets Monitor" className="rounded-2xl" />
        <h1 className="text-4xl font-medium tracking-tight">Pets Monitor</h1>
        <div className="space-y-4">{children}</div>
      </div>
    </div>
  )
}

export function Entrar() {
  const [ocupado, setOcupado] = useState(false)
  const params = new URLSearchParams(window.location.search + '&' + window.location.hash.replace(/^#/, ''))
  const [erro, setErro] = useState(params.get('error_description') ? 'Não foi possível entrar com o Google. Tente novamente.' : '')

  async function entrar() {
    setOcupado(true)
    setErro('')
    const { error } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: { redirectTo: window.location.origin, queryParams: { prompt: 'select_account' } },
    })
    if (error) {
      setOcupado(false)
      setErro(error.message)
    }
  }

  return (
    <TelaEntrada>
      <p className="text-white/60">Entre com sua conta Google para ver onde estão seus pets.</p>
      <button onClick={() => void entrar()} disabled={ocupado} className="flex w-full items-center justify-center gap-2 rounded-full bg-lime-300 py-3.5 font-medium text-black hover:bg-lime-200 disabled:opacity-50">
        <GoogleIcon /> {ocupado ? 'Abrindo o Google…' : 'Entrar com Google'}
      </button>
      {erro && <p className="text-[12px] font-medium text-rose-400">{erro}</p>}
    </TelaEntrada>
  )
}

export function SemAcesso({ email }: { email?: string }) {
  return (
    <TelaEntrada>
      <p className="text-white/60">
        {email ? <>O e-mail <strong>{email}</strong> não tem acesso.</> : 'Este e-mail não tem acesso.'} Peça ao administrador para liberar.
      </p>
      <button onClick={() => void supabase.auth.signOut()} className="w-full rounded-full bg-white/10 py-3.5 font-medium text-white/90 hover:bg-white/15">
        Sair e usar outra conta
      </button>
    </TelaEntrada>
  )
}

export function Carregando({ texto = 'Carregando…' }: { texto?: string }) {
  return (
    <TelaEntrada>
      <p className="text-white/50">{texto}</p>
    </TelaEntrada>
  )
}
