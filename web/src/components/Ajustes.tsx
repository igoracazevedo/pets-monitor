import { useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { supabase, type Camera, type Pet } from '../lib/supabase'
import { useDados } from '../lib/dados'

type Membro = { email: string; admin: boolean }

export default function Ajustes({ admin }: { admin: boolean }) {
  const { dados, recarregar } = useDados<{ pets: Pet[]; cams: Camera[]; membros: Membro[] }>(
    async () => {
      const [p, c, m] = await Promise.all([
        supabase.from('pm_pets').select('*').order('nome'),
        supabase.from('pm_cameras').select('*').order('ordem').order('nome'),
        supabase.from('pm_membros').select('*').order('email'),
      ])
      return { pets: (p.data ?? []) as Pet[], cams: (c.data ?? []) as Camera[], membros: (m.data ?? []) as Membro[] }
    },
    { pets: [], cams: [], membros: [] },
    60000,
  )
  const [email, setEmail] = useState('')
  const [msg, setMsg] = useState('')

  async function rodar(p: PromiseLike<{ error: { message: string } | null }>) {
    const { error } = await p
    setMsg(error ? error.message : '')
    await recarregar()
  }

  if (!admin) return <p className="vidro p-6 text-center text-slate-600">Só administradores alteram ajustes.</p>

  return (
    <div className="space-y-5">
      {msg && <p className="text-sm text-rose-600">{msg}</p>}

      <section className="vidro space-y-2 p-4">
        <h2 className="font-bold text-slate-900">Câmeras</h2>
        <ul className="space-y-2">
          {dados.cams.map((c) => (
            <li key={c.id} className="flex items-center justify-between gap-2 text-sm">
              <span>{c.nome}</span>
              <label className="flex items-center gap-1 text-[12px] text-slate-600">
                <input type="checkbox" checked={c.ativo} onChange={(e) => void rodar(supabase.from('pm_cameras').update({ ativo: e.target.checked }).eq('id', c.id))} />
                ativa
              </label>
            </li>
          ))}
        </ul>
        <p className="text-[12px] text-slate-500">As câmeras são cadastradas no <code>config.yaml</code> do programa de casa e aparecem aqui sozinhas.</p>
      </section>

      <section className="vidro space-y-3 p-4">
        <h2 className="font-bold text-slate-900">Quem pode acessar</h2>
        <ul className="space-y-2">
          {dados.membros.map((m) => (
            <li key={m.email} className="flex items-center justify-between gap-2 text-sm">
              <span className="truncate">
                {m.email}
                {m.admin ? ' · admin' : ''}
              </span>
              <button aria-label={`Remover ${m.email}`} className="text-rose-600" onClick={() => confirm(`Remover ${m.email}?`) && rodar(supabase.from('pm_membros').delete().eq('email', m.email))}>
                <Trash2 size={16} />
              </button>
            </li>
          ))}
        </ul>
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            if (!email.trim()) return
            void rodar(supabase.from('pm_membros').insert({ email: email.trim().toLowerCase() }))
            setEmail('')
          }}
        >
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="email@gmail.com" className="min-w-0 flex-1" />
          <button className="pilula" aria-label="Adicionar membro">
            <Plus size={16} />
          </button>
        </form>
      </section>
    </div>
  )
}
