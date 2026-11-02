import { useState } from 'react'
import { supabase, urlsDasFotos, type Avistamento, type Camera, type Pet } from '../lib/supabase'
import { useDados } from '../lib/dados'
import { dataHora, haQuanto } from '../lib/util'

type Dados = { pets: Pet[]; cams: Camera[]; lista: Avistamento[]; fotos: Record<string, string> }

export default function Historico() {
  const [pet, setPet] = useState('todos')
  const { dados, erro, carregando } = useDados<Dados>(
    async () => {
      let q = supabase.from('pm_avistamentos').select('*').order('visto_em', { ascending: false }).limit(80)
      if (pet === 'desconhecido') q = q.is('pet_id', null)
      else if (pet !== 'todos') q = q.eq('pet_id', pet)
      const [pets, cams, lista] = await Promise.all([supabase.from('pm_pets').select('*').order('nome'), supabase.from('pm_cameras').select('*'), q])
      if (lista.error) throw new Error(lista.error.message)
      const l = (lista.data ?? []) as Avistamento[]
      return { pets: (pets.data ?? []) as Pet[], cams: (cams.data ?? []) as Camera[], lista: l, fotos: await urlsDasFotos(l.slice(0, 40).map((a) => a.snapshot_path)) }
    },
    { pets: [], cams: [], lista: [], fotos: {} },
    20000,
  )
  const nomeCam = (id: string) => dados.cams.find((c) => c.id === id)?.nome ?? '—'
  const nomePet = (id: string | null) => (id ? (dados.pets.find((p) => p.id === id)?.nome ?? '—') : 'Animal não identificado')

  return (
    <div className="space-y-3">
      <select value={pet} onChange={(e) => setPet(e.target.value)} className="w-full sm:w-auto">
        <option value="todos">Todos</option>
        {dados.pets.map((p) => (
          <option key={p.id} value={p.id}>
            {p.nome}
          </option>
        ))}
        <option value="desconhecido">Não identificados</option>
      </select>
      {carregando ? (
        <p className="p-6 text-center text-slate-500">Carregando…</p>
      ) : erro ? (
        <p className="p-6 text-center text-rose-600">{erro}</p>
      ) : dados.lista.length === 0 ? (
        <p className="vidro p-6 text-center text-slate-500">Nenhum avistamento ainda.</p>
      ) : (
        <ul className="vidro divide-y divide-slate-200/70 overflow-hidden">
          {dados.lista.map((a) => (
            <li key={a.id} className="flex items-center gap-3 p-3">
              {a.snapshot_path && dados.fotos[a.snapshot_path] ? (
                <img src={dados.fotos[a.snapshot_path]} alt="" className="h-14 w-24 shrink-0 rounded-xl object-cover" loading="lazy" />
              ) : (
                <span className="h-14 w-24 shrink-0 rounded-xl bg-slate-100" />
              )}
              <div className="min-w-0 flex-1">
                <p className="truncate font-semibold text-slate-900">{nomePet(a.pet_id)}</p>
                <p className="truncate text-[12px] text-slate-500">
                  {nomeCam(a.camera_id)} · {dataHora(a.visto_em)} · {haQuanto(a.visto_em)}
                </p>
              </div>
              {a.confianca != null && <span className="shrink-0 text-[11px] text-slate-400">{Math.round(a.confianca * 100)}%</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
