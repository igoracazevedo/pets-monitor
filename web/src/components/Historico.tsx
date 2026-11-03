import { useState } from 'react'
import { marcarComoObjeto, supabase, urlsDasFotos, type Avistamento, type Camera, type Pet } from '../lib/supabase'
import { useDados } from '../lib/dados'
import { useVisualizador, type Caixa, type ItemFoto } from './Visualizador'
import { dataHora, haQuanto } from '../lib/util'

type Dados = { pets: Pet[]; cams: Camera[]; lista: Avistamento[]; fotos: Record<string, string>; gente: Record<string, string> }

export default function Historico({ admin }: { admin: boolean }) {
  const [pet, setPet] = useState('todos')
  const { dados, erro, carregando, recarregar } = useDados<Dados>(
    async () => {
      let q = supabase.from('pm_avistamentos').select('*').order('visto_em', { ascending: false }).limit(80)
      if (pet === 'pessoas') q = q.eq('especie', 'pessoa')
      else if (pet === 'desconhecido') q = q.is('pet_id', null).neq('especie', 'pessoa')
      else if (pet !== 'todos') q = q.eq('pet_id', pet)
      const [pets, cams, lista, gente] = await Promise.all([supabase.from('pm_pets').select('*').order('nome'), supabase.from('pm_cameras').select('*'), q, supabase.from('pm_pessoas').select('id,nome')])
      if (lista.error) throw new Error(lista.error.message)
      const l = (lista.data ?? []) as Avistamento[]
      return { pets: (pets.data ?? []) as Pet[], cams: (cams.data ?? []) as Camera[], lista: l, fotos: await urlsDasFotos(l.slice(0, 40).map((a) => a.snapshot_path)), gente: Object.fromEntries(((gente.data ?? []) as { id: string; nome: string }[]).map((g) => [g.id, g.nome])) }
    },
    { pets: [], cams: [], lista: [], fotos: {}, gente: {} },
    20000,
  )
  async function naoEPet(a: Avistamento) {
    if (a.x == null || a.y == null || a.w == null || a.h == null) return
    if (!confirm('Isso não é um pet? O app vai ignorar esse lugar nessa câmera e apagar os registros iguais.')) return
    try {
      const n = await marcarComoObjeto(a.camera_id, a.x, a.y, a.w, a.h)
      alert(n > 1 ? `Pronto. Apaguei também ${n - 1} registro(s) iguais desse lugar.` : 'Pronto. Esse lugar será ignorado.')
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Não consegui marcar.')
    }
    await recarregar()
  }

  /** "Quem é?": corrige o registro, acerta a última posição e manda a imagem para o programa de casa aprender. */
  async function corrigir(a: Avistamento, destino: string) {
    if (!destino) return
    const [tipo, id] = destino.split(':')
    try {
      const pet = tipo === 'pet' ? dados.pets.find((p) => p.id === id) : undefined
      const mudanca = tipo === 'pet' ? { pet_id: id, pessoa_id: null, especie: pet?.especie ?? 'cachorro', identificacao: 'manual' } : { pet_id: null, pessoa_id: id, especie: 'pessoa', identificacao: 'manual' }
      const up = await supabase.from('pm_avistamentos').update(mudanca).eq('id', a.id)
      if (up.error) throw up.error
      if (tipo === 'pet') {
        if (a.pet_id && a.pet_id !== id && a.snapshot_path) await supabase.from('pm_ultima_posicao').delete().eq('pet_id', a.pet_id).eq('snapshot_path', a.snapshot_path)
        const { data: atual } = await supabase.from('pm_ultima_posicao').select('visto_em').eq('pet_id', id).maybeSingle()
        if (!atual || atual.visto_em < a.visto_em)
          await supabase.from('pm_ultima_posicao').upsert({ pet_id: id, camera_id: a.camera_id, visto_em: a.visto_em, confianca: a.confianca, x: a.x, y: a.y, w: a.w, h: a.h, snapshot_path: a.snapshot_path, foto_em: a.visto_em })
      }
      if (a.snapshot_path && a.x != null && a.y != null && a.w != null && a.h != null)
        await supabase.from('pm_correcoes').insert({ avistamento_id: a.id, camera_id: a.camera_id, snapshot_path: a.snapshot_path, x: a.x, y: a.y, w: a.w, h: a.h, pet_id: tipo === 'pet' ? id : null, pessoa_id: tipo === 'pessoa' ? id : null })
    } catch (e) {
      alert(e instanceof Error ? e.message : (e as { message?: string })?.message ?? 'Não consegui corrigir.')
    }
    await recarregar()
  }

  const nomeCam = (id: string) => dados.cams.find((c) => c.id === id)?.nome ?? '—'
  const nomePet = (id: string | null, esp?: string | null, pessoa?: string | null) => (esp === 'pessoa' ? (pessoa ? (dados.gente[pessoa] ?? 'Pessoa') : 'Pessoa') : id ? (dados.pets.find((p) => p.id === id)?.nome ?? '—') : 'Animal não identificado')
  /** Marcação feita à mão na foto (vários animais/pessoas na mesma imagem): vira registro do histórico e amostra de aprendizado. */
  async function marcarNaFoto(item: ItemFoto, caixa: Caixa, destino: string) {
    const a = item.extra as Avistamento
    const [tipo, id] = destino.split(':')
    const pet = tipo === 'pet' ? dados.pets.find((p) => p.id === id) : undefined
    const box = { x: Number(caixa.x.toFixed(4)), y: Number(caixa.y.toFixed(4)), w: Number(caixa.w.toFixed(4)), h: Number(caixa.h.toFixed(4)) }
    const ins = await supabase.from('pm_avistamentos').insert({
      ...box,
      camera_id: a.camera_id,
      snapshot_path: a.snapshot_path,
      visto_em: a.visto_em,
      confianca: 1,
      identificacao: 'manual',
      especie: tipo === 'pessoa' ? 'pessoa' : (pet?.especie ?? 'cachorro'),
      pet_id: tipo === 'pet' ? id : null,
      pessoa_id: tipo === 'pessoa' ? id : null,
    })
    if (ins.error) throw ins.error
    if (tipo === 'pet') {
      const { data: atual } = await supabase.from('pm_ultima_posicao').select('visto_em').eq('pet_id', id).maybeSingle()
      if (!atual || atual.visto_em < a.visto_em)
        await supabase.from('pm_ultima_posicao').upsert({ pet_id: id, camera_id: a.camera_id, visto_em: a.visto_em, confianca: 1, ...box, snapshot_path: a.snapshot_path, foto_em: a.visto_em })
    }
    if (a.snapshot_path)
      await supabase.from('pm_correcoes').insert({ camera_id: a.camera_id, snapshot_path: a.snapshot_path, ...box, pet_id: tipo === 'pet' ? id : null, pessoa_id: tipo === 'pessoa' ? id : null })
    await recarregar()
  }
  const opcoes = [...dados.pets.map((p) => ({ valor: `pet:${p.id}`, nome: p.nome })), ...Object.entries(dados.gente).map(([id, nome]) => ({ valor: `pessoa:${id}`, nome }))]
  const { abrir, janela } = useVisualizador(admin ? { opcoes, onMarcar: marcarNaFoto } : undefined)
  const verFoto = (a: Avistamento) => {
    const com = dados.lista.filter((x) => x.snapshot_path && dados.fotos[x.snapshot_path])
    abrir(
      com.map((x) => ({ id: String(x.id), url: dados.fotos[x.snapshot_path!], titulo: nomePet(x.pet_id, x.especie, x.pessoa_id), legenda: `${nomeCam(x.camera_id)} · ${dataHora(x.visto_em)}`, extra: x })),
      Math.max(0, com.findIndex((x) => x.id === a.id)),
    )
  }

  return (
    <div className="space-y-3">
      {janela}
      <select value={pet} onChange={(e) => setPet(e.target.value)} className="w-full sm:w-auto">
        <option value="todos">Todos</option>
        {dados.pets.map((p) => (
          <option key={p.id} value={p.id}>
            {p.nome}
          </option>
        ))}
        <option value="desconhecido">Não identificados</option>
        <option value="pessoas">Pessoas</option>
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
                <button type="button" className="shrink-0" onClick={() => verFoto(a)} aria-label="Ver foto">
                  <img src={dados.fotos[a.snapshot_path]} alt="" className="h-14 w-24 rounded-xl object-cover" loading="lazy" />
                </button>
              ) : (
                <span className="h-14 w-24 shrink-0 rounded-xl bg-slate-100" />
              )}
              <div className="min-w-0 flex-1">
                <p className="truncate font-semibold text-slate-900">{nomePet(a.pet_id, a.especie, a.pessoa_id)}</p>
                <p className="truncate text-[12px] text-slate-500">
                  {nomeCam(a.camera_id)} · {dataHora(a.visto_em)} · {haQuanto(a.visto_em)}
                </p>
              </div>
              {admin && (
                <div className="flex shrink-0 flex-col items-end gap-1">
                  <select
                    aria-label="Quem foi encontrado"
                    className="max-w-[110px] !px-2 !py-1 text-[11px]"
                    value=""
                    onChange={(e) => void corrigir(a, e.target.value)}
                  >
                    <option value="">Quem é?</option>
                    <optgroup label="Pets">
                      {dados.pets.map((p) => (
                        <option key={p.id} value={`pet:${p.id}`}>
                          {p.nome}
                        </option>
                      ))}
                    </optgroup>
                    {Object.keys(dados.gente).length > 0 && (
                      <optgroup label="Pessoas">
                        {Object.entries(dados.gente).map(([id, nome]) => (
                          <option key={id} value={`pessoa:${id}`}>
                            {nome}
                          </option>
                        ))}
                      </optgroup>
                    )}
                  </select>
                  <button className="text-[11px] font-semibold text-rose-600" onClick={() => void naoEPet(a)}>
                    Não é pet
                  </button>
                </div>
              )}
              {a.confianca != null && <span className="shrink-0 text-[11px] text-slate-400">{Math.round(a.confianca * 100)}%</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
