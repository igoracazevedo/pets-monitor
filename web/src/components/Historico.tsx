import { useState } from 'react'
import { marcarComoObjeto, supabase, urlsDasFotos, type Avistamento, type Camera, type Pet, type Zona } from '../lib/supabase'
import { useDados } from '../lib/dados'
import { useVisualizador, type Caixa, type ItemFoto } from './Visualizador'
import { dataHora, haQuanto } from '../lib/util'
import { corPadraoPet, corValida } from '../lib/cores'

const CINCO_MIN = 5 * 60 * 1000
/** Mostra uma foto por câmera + quem (pet/pessoa) a cada 5 minutos: o resto é a mesma cena repetida. */
function semRepetidas(l: Avistamento[]): Avistamento[] {
  const ultimo = new Map<string, number>()
  return l.filter((a) => {
    const k = `${a.camera_id}|${a.pet_id ?? a.pessoa_id ?? a.especie ?? ''}`
    const t = new Date(a.visto_em).getTime()
    const u = ultimo.get(k)
    if (u !== undefined && u - t < CINCO_MIN) return false
    ultimo.set(k, t)
    return true
  })
}

type Dados = { pets: Pet[]; cams: Camera[]; lista: Avistamento[]; fotos: Record<string, string>; gente: Record<string, string>; zonas: Zona[] }

export default function Historico({ admin }: { admin: boolean }) {
  const [pet, setPet] = useState('todos')
  const { dados, erro, carregando, recarregar } = useDados<Dados>(
    async () => {
      let q = supabase.from('pm_avistamentos').select('*').order('visto_em', { ascending: false }).limit(300)
      if (pet === 'pessoas') q = q.eq('especie', 'pessoa')
      else if (pet === 'desconhecido') q = q.is('pet_id', null).neq('especie', 'pessoa')
      else if (pet !== 'todos') q = q.eq('pet_id', pet)
      const [pets, cams, lista, gente, zonas] = await Promise.all([supabase.from('pm_pets').select('*').order('nome'), supabase.from('pm_cameras').select('*'), q, supabase.from('pm_pessoas').select('id,nome'), supabase.from('pm_zonas').select('*')])
      if (lista.error) throw new Error(lista.error.message)
      const l = semRepetidas((lista.data ?? []) as Avistamento[]).slice(0, 60)
      return { pets: (pets.data ?? []) as Pet[], cams: (cams.data ?? []) as Camera[], lista: l, fotos: await urlsDasFotos(l.slice(0, 40).map((a) => a.snapshot_path)), gente: Object.fromEntries(((gente.data ?? []) as { id: string; nome: string }[]).map((g) => [g.id, g.nome])), zonas: (zonas.data ?? []) as Zona[] }
    },
    { pets: [], cams: [], lista: [], fotos: {}, gente: {}, zonas: [] },
    20000,
  )
  async function naoEPet(a: Avistamento) {
    if (a.x == null || a.y == null || a.w == null || a.h == null) return
    if (!confirm(a.especie === 'pessoa' ? 'Não há pessoa aqui? O app vai ignorar esse lugar nessa câmera e apagar os registros iguais.' : 'Isso não é um pet? O app vai ignorar esse lugar nessa câmera e apagar os registros iguais.')) return
    try {
      const n = await marcarComoObjeto(a.camera_id, a.x, a.y, a.w, a.h)
      alert(n > 1 ? `Pronto. Apaguei também ${n - 1} registro(s) iguais desse lugar.` : 'Pronto. Esse lugar será ignorado.')
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Não consegui marcar.')
    }
    await recarregar()
  }

  /** Registra um evento (bebeu água, xixi, cocô) a partir de um registro do Histórico: usa o pet, a câmera, a foto e a hora dele. */
  async function registrarEvento(a: Avistamento, tipo: string) {
    if (!tipo) return
    if (!a.pet_id) {
      alert('Primeiro diga quem é (Quem é?), depois registre o evento.')
      return
    }
    const nome = dados.pets.find((p) => p.id === a.pet_id)?.nome ?? 'O pet'
    const texto = tipo === 'agua' ? 'bebeu água' : tipo === 'xixi' ? 'fez xixi' : 'fez cocô'
    if (!confirm(`Registrar que ${nome} ${texto} em ${nomeCam(a.camera_id)} às ${dataHora(a.visto_em)}?`)) return
    const { error } = await supabase.from('pm_banheiro_eventos').insert({ camera_id: a.camera_id, tipo, pet_id: a.pet_id, snapshot_path: a.snapshot_path, visto_em: a.visto_em })
    alert(error ? `Não consegui registrar: ${error.message}` : 'Evento registrado. Veja no menu Eventos.')
  }

  /** Remove o registro do histórico (e o arquivo da foto, se mais nada usa ela). */
  async function remover(a: Avistamento) {
    if (!confirm('Remover esta foto do histórico?')) return
    try {
      const del = await supabase.from('pm_avistamentos').delete().eq('id', a.id)
      if (del.error) throw del.error
      if (a.snapshot_path && a.snapshot_path.startsWith('avistamentos/')) {
        const [outros, pos] = await Promise.all([
          supabase.from('pm_avistamentos').select('id', { count: 'exact', head: true }).eq('snapshot_path', a.snapshot_path),
          supabase.from('pm_ultima_posicao').select('pet_id', { count: 'exact', head: true }).eq('snapshot_path', a.snapshot_path),
        ])
        if (!outros.count && !pos.count) await supabase.storage.from('pm-snapshots').remove([a.snapshot_path])
      }
    } catch (e) {
      alert(e instanceof Error ? e.message : (e as { message?: string })?.message ?? 'Não consegui remover.')
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
    if (destino.startsWith('zona:')) {
      const [, tipo, quem] = destino.split(':')
      const z = await supabase.from('pm_zonas').insert({ camera_id: a.camera_id, tipo, pet_id: quem === 'todos' ? null : quem, x: Number(caixa.x.toFixed(4)), y: Number(caixa.y.toFixed(4)), w: Number(caixa.w.toFixed(4)), h: Number(caixa.h.toFixed(4)) })
      if (z.error) throw z.error
      await recarregar()
      return
    }
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
  const TIPOS_ZONA = { banheiro: 'Banheiro', bebedouro: 'Bebedouro', comedouro: 'Comedouro', cama: 'Cama' } as const
  const corDoPet = (id: string | null) => {
    const i = dados.pets.findIndex((p) => p.id === id)
    return i < 0 ? '#9ca3af' : corValida(dados.pets[i].cor) ? dados.pets[i].cor! : corPadraoPet(i)
  }
  const rotuloZona = (z: Zona) => `${TIPOS_ZONA[z.tipo]} ${z.pet_id ? `da ${dados.pets.find((p) => p.id === z.pet_id)?.nome ?? '?'}` : '(das duas)'}`
  const opcoes = [
    ...dados.pets.map((p) => ({ valor: `pet:${p.id}`, nome: p.nome, grupo: 'Quem é' })),
    ...Object.entries(dados.gente).map(([id, nome]) => ({ valor: `pessoa:${id}`, nome, grupo: 'Quem é' })),
    ...(Object.keys(TIPOS_ZONA) as (keyof typeof TIPOS_ZONA)[]).flatMap((t) => [
      ...dados.pets.map((p) => ({ valor: `zona:${t}:${p.id}`, nome: `${TIPOS_ZONA[t]} da ${p.nome}`, grupo: 'Marcar local' })),
      { valor: `zona:${t}:todos`, nome: `${TIPOS_ZONA[t]} (das duas)`, grupo: 'Marcar local' },
    ]),
  ]
  const { abrir, janela } = useVisualizador(admin ? { opcoes, onMarcar: marcarNaFoto } : undefined)
  const verFoto = (a: Avistamento) => {
    const com = dados.lista.filter((x) => x.snapshot_path && dados.fotos[x.snapshot_path])
    abrir(
      com.map((x) => ({ id: String(x.id), url: dados.fotos[x.snapshot_path!], titulo: nomePet(x.pet_id, x.especie, x.pessoa_id), legenda: `${nomeCam(x.camera_id)} · ${dataHora(x.visto_em)}`, extra: x, locais: dados.zonas.filter((z) => z.camera_id === x.camera_id).map((z) => ({ caixa: { x: Number(z.x), y: Number(z.y), w: Number(z.w), h: Number(z.h) }, rotulo: rotuloZona(z), cor: corDoPet(z.pet_id) })) })),
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
      {admin && dados.zonas.length > 0 && (
        <details className="vidro px-4 py-2 text-[13px]">
          <summary className="cursor-pointer font-semibold text-slate-800">Locais marcados ({dados.zonas.length})</summary>
          <ul className="divide-y divide-slate-200/70 pt-1">
            {dados.zonas.map((z) => (
              <li key={z.id} className="flex items-center justify-between gap-2 py-1.5">
                <span className="flex min-w-0 items-center gap-2">
                  <span className="h-3 w-3 shrink-0 rounded-full" style={{ background: corDoPet(z.pet_id) }} />
                  <span className="truncate">
                    {rotuloZona(z)} · {nomeCam(z.camera_id)}
                  </span>
                </span>
                <button className="shrink-0 text-[12px] font-semibold text-rose-600" onClick={async () => { if (confirm('Remover este local?')) { await supabase.from('pm_zonas').delete().eq('id', z.id); await recarregar() } }}>
                  Remover
                </button>
              </li>
            ))}
          </ul>
        </details>
      )}
      {carregando ? (
        <p className="p-6 text-center text-slate-500">Carregando…</p>
      ) : erro ? (
        <p className="p-6 text-center text-rose-600">{erro}</p>
      ) : dados.lista.length === 0 ? (
        <p className="vidro p-6 text-center text-slate-500">Nenhum avistamento ainda.</p>
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {dados.lista.map((a) => (
            <li key={a.id} className="vidro overflow-hidden">
              {a.snapshot_path && dados.fotos[a.snapshot_path] ? (
                <button type="button" className="block w-full" onClick={() => verFoto(a)} aria-label="Ver foto">
                  <img src={dados.fotos[a.snapshot_path]} alt="" className="aspect-video w-full object-cover" loading="lazy" />
                </button>
              ) : (
                <div className="aspect-video w-full bg-slate-100" />
              )}
              <div className="space-y-2 p-3">
                <div className="flex items-baseline justify-between gap-2">
                  <p className="truncate font-semibold text-slate-900">{nomePet(a.pet_id, a.especie, a.pessoa_id)}</p>
                  {a.confianca != null && <span className="shrink-0 text-[11px] text-slate-400">{Math.round(a.confianca * 100)}%</span>}
                </div>
                <p className="text-[12px] text-slate-500">
                  {nomeCam(a.camera_id)} · {dataHora(a.visto_em)} · {haQuanto(a.visto_em)}
                </p>
                {admin && (
                  <div className="flex items-center gap-2">
                    <select aria-label="Quem foi encontrado" className="min-w-0 flex-1 !px-2 !py-1.5 text-[13px]" value="" onChange={(e) => void corrigir(a, e.target.value)}>
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
                    <button className="shrink-0 rounded-lg px-2 py-1.5 text-[12px] font-semibold text-rose-600 ring-1 ring-rose-200" onClick={() => void naoEPet(a)}>
                      {a.especie === 'pessoa' ? 'Não é pessoa' : 'Não é pet'}
                    </button>
                    <button className="shrink-0 rounded-lg px-2 py-1.5 text-[12px] font-semibold text-slate-600 ring-1 ring-slate-200" onClick={() => void remover(a)} aria-label="Remover foto">
                      Remover
                    </button>
                  </div>
                )}
                {admin && (
                  <select aria-label="Registrar evento" className="w-full !px-2 !py-1.5 text-[13px]" value="" onChange={(e) => void registrarEvento(a, e.target.value)}>
                    <option value="">Registrar evento…</option>
                    <option value="agua">Bebeu água</option>
                    <option value="xixi">Fez xixi</option>
                    <option value="coco">Fez cocô</option>
                  </select>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
