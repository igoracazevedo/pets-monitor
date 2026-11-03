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
    <div className="flex min-h-dvh flex-col bg-[#0e7490]">
      <div className="flex flex-col items-center px-4 pb-10 pt-14 text-white">
        <img src="/icon-192.png" width={72} height={72} alt="Pets Monitor" style={{ borderRadius: 72 * 0.22 }} />
        <h1 className="mt-4 text-lg font-extrabold tracking-tight">Pets Monitor IAZ</h1>
      </div>
      <div className="folha flex-1 rounded-t-[26px] px-4 pt-6">
        <div className="vidro mx-auto max-w-sm space-y-4 p-4 text-center">{children}</div>
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
      <p className="text-slate-600">Entre com sua conta Google para ver onde estão seus pets.</p>
      <button onClick={() => void entrar()} disabled={ocupado} className="vidro flex w-full items-center justify-center gap-2 py-2.5 font-semibold text-slate-700 disabled:opacity-50" style={{ borderRadius: 14 }}>
        <GoogleIcon /> {ocupado ? 'Abrindo o Google…' : 'Entrar com Google'}
      </button>
      {erro && <p className="text-[12px] font-medium text-rose-600">{erro}</p>}
    </TelaEntrada>
  )
}

export function SemAcesso({ email }: { email?: string }) {
  return (
    <TelaEntrada>
      <p className="text-slate-600">
        {email ? <>O e-mail <strong>{email}</strong> não tem acesso.</> : 'Este e-mail não tem acesso.'} Peça ao administrador para liberar.
      </p>
      <button onClick={() => void supabase.auth.signOut()} className="vidro w-full py-2.5 font-semibold text-slate-700" style={{ borderRadius: 14 }}>
        Sair e usar outra conta
      </button>
    </TelaEntrada>
  )
}

export function Carregando({ texto = 'Carregando…' }: { texto?: string }) {
  return (
    <TelaEntrada>
      <p className="text-slate-500">{texto}</p>
    </TelaEntrada>
  )
}
