import { useState } from 'react'
import { Cat, Dog, RefreshCw } from 'lucide-react'
import { supabase, urlsDasFotos, type Camera, type Pet, type Posicao } from '../lib/supabase'
import { useDados } from '../lib/dados'
import { dataHora, haQuanto, minutosDesde } from '../lib/util'

type Dados = { pets: Pet[]; pos: Posicao[]; cams: Camera[]; fotos: Record<string, string>; desconhecidos: number }

async function carregar(): Promise<Dados> {
  const [pets, pos, cams, desc] = await Promise.all([
    supabase.from('pm_pets').select('*').eq('ativo', true).order('nome'),
    supabase.from('pm_ultima_posicao').select('*'),
    supabase.from('pm_cameras').select('*'),
    supabase
      .from('pm_avistamentos')
      .select('id', { count: 'exact', head: true })
      .is('pet_id', null)
      .gte('visto_em', new Date(Date.now() - 3600_000).toISOString()),
  ])
  if (pets.error) throw new Error(pets.error.message)
  const p = (pos.data ?? []) as Posicao[]
  return {
    pets: (pets.data ?? []) as Pet[],
    pos: p,
    cams: (cams.data ?? []) as Camera[],
    fotos: await urlsDasFotos(p.map((x) => x.snapshot_path)),
    desconhecidos: desc.count ?? 0,
  }
}

export default function Inicio() {
  const [buscando, setBuscando] = useState(false)
  const { dados, erro, carregando, recarregar } = useDados(carregar, { pets: [], pos: [], cams: [], fotos: {}, desconhecidos: 0 })
  if (carregando) return <p className="p-6 text-center text-slate-500">Carregando…</p>
  if (erro) return <p className="p-6 text-center text-rose-600">{erro}</p>
  if (dados.pets.length === 0)
    return <p className="vidro p-6 text-center text-slate-600">Nenhum pet cadastrado ainda. Vá em <strong>Ajustes</strong> ou rode <code>python -m pets_agent ensinar</code> no computador de casa.</p>

  async function localizar() {
    setBuscando(true)
    try {
      const { data, error } = await supabase.from('pm_pedidos').insert({}).select('id').single()
      if (error || !data) throw error
      for (let i = 0; i < 25; i++) { // até ~50 s esperando o programa de casa varrer as câmeras
        await new Promise((r) => setTimeout(r, 2000))
        const { data: p } = await supabase.from('pm_pedidos').select('atendido_em').eq('id', data.id).single()
        if (p?.atendido_em) break
      }
      await recarregar()
    } finally {
      setBuscando(false)
    }
  }

  const cam = (id: string | null) => dados.cams.find((c) => c.id === id)
  return (
    <div className="space-y-4">
      <button className="pilula" disabled={buscando} onClick={() => void localizar()}>
        <RefreshCw size={16} className={buscando ? 'animate-spin' : ''} /> {buscando ? 'Procurando nas câmeras…' : 'Onde estão agora?'}
      </button>
      <div className="grid gap-4 sm:grid-cols-2">
        {dados.pets.map((pet) => {
          const pos = dados.pos.find((p) => p.pet_id === pet.id)
          const c = cam(pos?.camera_id ?? null)
          const recente = minutosDesde(pos?.visto_em) < 2
          const Icone = pet.especie === 'gato' ? Cat : Dog
          return (
            <article key={pet.id} className="vidro overflow-hidden">
              <div className="flex items-center gap-3 p-4">
                <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-cyan-700/10 text-cyan-800">
                  <Icone size={22} strokeWidth={1.9} />
                </span>
                <div className="min-w-0 flex-1">
                  <h2 className="truncate text-lg font-extrabold text-slate-900">{pet.nome}</h2>
                  {pos ? (
                    <p className="truncate text-[13px] text-slate-600">
                      <strong className="text-slate-900">{c?.nome ?? 'Câmera removida'}</strong>
                      {c?.ambiente ? ` · ${c.ambiente}` : ''}
                    </p>
                  ) : (
                    <p className="text-[13px] text-slate-500">Ainda não foi visto</p>
                  )}
                </div>
                {pos && (
                  <span className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] font-bold ${recente ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-600'}`}>
                    {recente ? 'Agora' : haQuanto(pos.visto_em)}
                  </span>
                )}
              </div>
              {pos?.snapshot_path && dados.fotos[pos.snapshot_path] && (
                <img src={dados.fotos[pos.snapshot_path]} alt={`${pet.nome} na última posição`} className="aspect-video w-full object-cover" />
              )}
              {pos && <p className="px-4 py-2 text-[11px] text-slate-500">Última posição registrada em {dataHora(pos.visto_em)}</p>}
            </article>
          )
        })}
      </div>
      {dados.desconhecidos > 0 && (
        <p className="vidro px-4 py-3 text-[12px] text-slate-600">
          {dados.desconhecidos} avistamento(s) de animal sem identificação na última hora. Veja no Histórico.
        </p>
      )}
    </div>
  )
}
