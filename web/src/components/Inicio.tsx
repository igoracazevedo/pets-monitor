import { useState } from 'react'
import { Cat, Dog, RefreshCw, Users } from 'lucide-react'
import { marcarComoObjeto, supabase, urlsDasFotos, urlsDosPets, type Camera, type EventoBanheiro, type Pet, type Posicao, type Presenca } from '../lib/supabase'
import { useDados } from '../lib/dados'
import { useVisualizador } from './Visualizador'
import { dataHora, haQuanto, minutosDesde } from '../lib/util'

type Dados = { pets: Pet[]; pos: Posicao[]; cams: Camera[]; fotos: Record<string, string>; perfis: Record<string, string>; desconhecidos: number; gente: Presenca[]; banheiro: EventoBanheiro[] }

/** Exemplos ensinados pelo comando ("xixi no Banheiro") ficam em banheiro/ e não são ocorrências de verdade. */
const exemplo = (e: EventoBanheiro) => !!e.snapshot_path?.startsWith('banheiro/')
const TEXTO_EVENTO = { xixi: 'fez xixi', coco: 'fez cocô', agua: 'bebeu água' } as const
const textoEvento = (e: EventoBanheiro, nome: string | undefined) =>
  e.tipo === 'limpo' ? 'Tapete limpo' : nome ? `${nome} ${TEXTO_EVENTO[e.tipo]}` : e.tipo === 'agua' ? 'Uma das cachorras bebeu água' : `${e.tipo === 'coco' ? 'Cocô' : 'Xixi'} (não sei quem fez)`

/** Fotos que ilustram os avisos: a mais recente de cada câmera do banheiro e o último quadro das câmeras sem sinal. */
function fotosDosAvisos(ev: EventoBanheiro[], cams: Camera[]): (string | null)[] {
  const ultimas = new Map<string, string>()
  for (const e of ev) if (e.snapshot_path && !ultimas.has(`${e.camera_id}|${e.tipo}`)) ultimas.set(`${e.camera_id}|${e.tipo}`, e.snapshot_path)
  const quadros = cams.filter((c) => c.ultimo_quadro_path && (c.ultimo_status === 'erro' || ev.some((e) => e.camera_id === c.id))).map((c) => c.ultimo_quadro_path)
  const recentes = ev.filter((e) => !exemplo(e)).slice(0, 20).map((e) => e.snapshot_path)
  return [...ultimas.values(), ...quadros, ...recentes]
}

async function carregar(): Promise<Dados> {
  const [pets, pos, cams, desc, presenca, banheiro] = await Promise.all([
    supabase.from('pm_pets').select('*').eq('ativo', true).order('nome'),
    supabase.from('pm_ultima_posicao').select('*'),
    supabase.from('pm_cameras').select('*'),
    supabase
      .from('pm_avistamentos')
      .select('id', { count: 'exact', head: true })
      .is('pet_id', null)
      .neq('especie', 'pessoa')
      .gte('visto_em', new Date(Date.now() - 3600_000).toISOString()),
    supabase.from('pm_presenca').select('*'),
    supabase.from('pm_banheiro_eventos').select('*').gte('visto_em', new Date(Date.now() - 7 * 86400_000).toISOString()).order('visto_em', { ascending: false }).limit(80),
  ])
  if (pets.error) throw new Error(pets.error.message)
  const p = (pos.data ?? []) as Posicao[]
  const gente = ((presenca.data ?? []) as Presenca[]).filter((g) => g.ultima_vez).sort((a, b) => (b.ultima_vez ?? '').localeCompare(a.ultima_vez ?? ''))
  return {
    pets: (pets.data ?? []) as Pet[],
    pos: p,
    cams: (cams.data ?? []) as Camera[],
    banheiro: (banheiro.data ?? []) as EventoBanheiro[],
    fotos: await urlsDasFotos([...p.map((x) => x.snapshot_path), ...gente.map((g) => g.snapshot_path), ...fotosDosAvisos((banheiro.data ?? []) as EventoBanheiro[], (cams.data ?? []) as Camera[])]),
    gente,
    perfis: await urlsDosPets(((pets.data ?? []) as Pet[]).map((x) => x.foto_perfil_path)),
    desconhecidos: desc.count ?? 0,
  }
}

type Aviso = { texto: string; tom: 'ok' | 'alerta' | 'erro'; foto?: string | null; quando?: string; titulo?: string }
const lista = (n: string[]) => (n.length > 1 ? `${n.slice(0, -1).join(', ')} e ${n[n.length - 1]}` : (n[0] ?? ''))

/** Avisos da tela Início: estado do banheiro (desde a última limpeza) e câmeras sem sinal. */
function montarAvisos(d: Dados, cam: (id: string | null) => Camera | undefined): Aviso[] {
  const out: Aviso[] = []
  const porCamera = new Map<string, EventoBanheiro[]>()
  for (const e of d.banheiro.filter((x) => x.tipo !== 'agua')) porCamera.set(e.camera_id, [...(porCamera.get(e.camera_id) ?? []), e])
  for (const [cid, evs] of porCamera) {
    const nome = cam(cid)?.nome ?? 'Banheiro'
    const iLimpo = evs.findIndex((e) => e.tipo === 'limpo') // eventos vêm do mais novo para o mais antigo
    const sujos = iLimpo < 0 ? evs : evs.slice(0, iLimpo)
    if (sujos.length === 0) {
      if (evs[0]) out.push({ texto: `${nome}: limpo desde ${dataHora(evs[0].visto_em)}.`, tom: 'ok', foto: evs.find((e) => e.snapshot_path)?.snapshot_path ?? cam(cid)?.ultimo_quadro_path, quando: evs[0].visto_em, titulo: nome })
      continue
    }
    const tipos = ['xixi', 'coco'].filter((t) => sujos.some((e) => e.tipo === t)).map((t) => (t === 'coco' ? 'cocô' : 'xixi'))
    const quem = [...new Set(sujos.map((e) => d.pets.find((p) => p.id === e.pet_id)?.nome).filter((n): n is string => !!n))]
    out.push({ texto: `${nome}: sujo de ${tipos.join(' e ')}${quem.length ? `, feito por ${lista(quem)}` : ', não sei quem fez'}. Último às ${dataHora(sujos[0].visto_em)}.`, tom: 'alerta', foto: sujos.find((e) => e.snapshot_path)?.snapshot_path ?? cam(cid)?.ultimo_quadro_path, quando: sujos[0].visto_em, titulo: nome })
  }
  const agua = d.banheiro.find((e) => e.tipo === 'agua' && Date.now() - new Date(e.visto_em).getTime() < 86400_000)
  if (agua) {
    const quem = d.pets.find((p) => p.id === agua.pet_id)?.nome
    out.push({ texto: `${quem ?? 'Uma das cachorras'} bebeu água às ${dataHora(agua.visto_em)}.`, tom: 'ok', foto: agua.snapshot_path, quando: agua.visto_em, titulo: quem ? `${quem} bebendo água` : 'Bebendo água' })
  }
  for (const c of d.cams) if (c.ativo && c.ultimo_status === 'erro') out.push({ texto: `Câmera ${c.nome} sem sinal${c.ultima_leitura ? ` desde ${dataHora(c.ultima_leitura)}` : ''}.`, tom: 'erro', foto: c.ultimo_quadro_path, quando: c.ultima_leitura ?? undefined, titulo: c.nome })
  return out
}

export default function Inicio({ admin }: { admin: boolean }) {
  const [buscando, setBuscando] = useState(false)
  const [texto, setTexto] = useState('')
  const [comandando, setComandando] = useState(false)
  const [resposta, setResposta] = useState('')
  const [verTodos, setVerTodos] = useState(false)
  const { abrir, janela } = useVisualizador()
  const { dados, erro, carregando, recarregar } = useDados(carregar, { pets: [], pos: [], cams: [], fotos: {}, perfis: {}, desconhecidos: 0, gente: [], banheiro: [] })
  if (carregando) return <p className="p-6 text-center text-slate-500">Carregando…</p>
  if (erro) return <p className="p-6 text-center text-rose-600">{erro}</p>
  const pessoasAgora = dados.gente.filter((g) => g.pessoas > 0 && minutosDesde(g.ultima_vez) < 3)
  const ultimaPessoa = dados.gente[0]
  const nomeCam = (id: string) => dados.cams.find((c) => c.id === id)?.nome ?? 'Câmera removida'
  const secaoPessoas = (
    <section className="vidro space-y-2 p-4">
      <h2 className="flex items-center gap-2 font-bold text-slate-900">
        <Users size={18} strokeWidth={1.9} className="text-cyan-800" /> Pessoas
      </h2>
      {pessoasAgora.length > 0 ? (
        <ul className="space-y-2">
          {pessoasAgora.map((g) => (
            <li key={g.camera_id} className="flex items-center gap-3">
              {g.snapshot_path && dados.fotos[g.snapshot_path] && (
                <button type="button" className="shrink-0" onClick={() => abrir([{ id: g.camera_id, url: dados.fotos[g.snapshot_path!], titulo: g.quem || 'Pessoa', legenda: `${nomeCam(g.camera_id)} · ${g.foto_em ? dataHora(g.foto_em) : ''}` }])} aria-label="Ver foto">
                  <img src={dados.fotos[g.snapshot_path]} alt="" className="h-12 w-20 rounded-xl object-cover" />
                </button>
              )}
              <p className="min-w-0 text-sm text-slate-700">
                <strong className="text-slate-900">{nomeCam(g.camera_id)}</strong> · {g.quem ? g.quem : `${g.pessoas} ${g.pessoas === 1 ? 'pessoa' : 'pessoas'}`} agora
              </p>
            </li>
          ))}
        </ul>
      ) : ultimaPessoa ? (
        <div className="space-y-2">
          <p className="text-sm text-slate-600">Ninguém nas câmeras agora. Últimas vezes que apareceram:</p>
          <ul className="space-y-2">
            {dados.gente.slice(0, 3).map((g) => (
              <li key={g.camera_id} className="flex items-center gap-3">
                {g.snapshot_path && dados.fotos[g.snapshot_path] && (
                  <button type="button" className="shrink-0" onClick={() => abrir([{ id: g.camera_id, url: dados.fotos[g.snapshot_path!], titulo: g.quem || 'Pessoa', legenda: `${nomeCam(g.camera_id)} · ${dataHora(g.ultima_vez ?? g.foto_em ?? '')}` }])} aria-label="Ver foto">
                    <img src={dados.fotos[g.snapshot_path]} alt="" className="h-12 w-20 rounded-xl object-cover" />
                  </button>
                )}
                <p className="min-w-0 text-sm text-slate-700">
                  <strong className="text-slate-900">{nomeCam(g.camera_id)}</strong>
                  {g.quem ? ` · ${g.quem}` : ''}
                  <br />
                  <span className="text-[12px] text-slate-500">
                    {dataHora(g.ultima_vez ?? '')} · {haQuanto(g.ultima_vez)}
                  </span>
                </p>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="text-sm text-slate-500">Nenhuma pessoa vista nas câmeras ainda.</p>
      )}
    </section>
  )

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

  const sem = (t: string) => t.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase()
  async function pedir(linha: Record<string, string>, aviso: string) {
    setComandando(true)
    setResposta(aviso)
    try {
      const { data, error } = await supabase.from('pm_pedidos').insert(linha).select('id').single()
      if (error || !data) throw error ?? new Error('Não consegui enviar o pedido.')
      let msg = 'O programa de casa não respondeu. Confira se o iniciar.bat está aberto.'
      for (let i = 0; i < 30; i++) {
        await new Promise((r) => setTimeout(r, 2000))
        const { data: p } = await supabase.from('pm_pedidos').select('atendido_em,resultado').eq('id', data.id).single()
        if (p?.atendido_em) {
          msg = p.resultado ?? 'Pronto.'
          break
        }
      }
      setResposta(msg)
      setTexto('')
      await recarregar()
    } catch (e) {
      setResposta(e instanceof Error ? e.message : (e as { message?: string })?.message ?? 'Erro ao enviar.')
    } finally {
      setComandando(false)
    }
  }
  /** Linha de comando: "Mavi na Sala" -> o programa de casa tira a foto de agora da câmera, marca o pet e aprende com ela. */
  async function comando() {
    const t = sem(texto)
    const rotulo = (['xixi', 'coco', 'limpo'] as const).find((r) => new RegExp(`\\b${r}\\b`).test(t))
    if (rotulo) {
      const bs = dados.cams.filter((c) => sem(c.nome).includes('banheiro'))
      const cam = [...dados.cams].sort((a, b) => b.nome.length - a.nome.length).find((c) => t.includes(sem(c.nome))) ?? (bs.length === 1 ? bs[0] : undefined)
      if (!cam) {
        setResposta(`Qual câmera? Escreva, por exemplo: "${rotulo} no ${bs[0]?.nome ?? 'Banheiro'}".`)
        return
      }
      await pedir({ tipo: 'ensinar_banheiro', camera_id: cam.id, rotulo }, `Ensinando "${rotulo}" na câmera ${cam.nome}…`)
      return
    }
    const pet = [...dados.pets].sort((a, b) => b.nome.length - a.nome.length).find((p) => t.includes(sem(p.nome)))
    const camera = [...dados.cams].sort((a, b) => b.nome.length - a.nome.length).find((c) => t.includes(sem(c.nome)))
    if (!pet || !camera) {
      setResposta(`Não entendi. Escreva o pet e a câmera, por exemplo: "${dados.pets[0]?.nome ?? 'Mavi'} na ${dados.cams[0]?.nome ?? 'Sala'}". ${!pet ? 'Pets: ' + dados.pets.map((p) => p.nome).join(', ') + '. ' : ''}${!camera ? 'Câmeras: ' + dados.cams.map((c) => c.nome).join(', ') + '.' : ''}`)
      return
    }
    await pedir({ tipo: 'identificar', pet_id: pet.id, camera_id: camera.id }, `Procurando ${pet.nome} na câmera ${camera.nome}…`)
  }

  async function naoEPet(pos: Posicao) {
    if (!pos.camera_id || pos.x == null || pos.y == null || pos.w == null || pos.h == null) return
    if (!confirm('Isso não é este pet? O app vai ignorar esse lugar nessa câmera e apagar os registros iguais.')) return
    try {
      const n = await marcarComoObjeto(pos.camera_id, pos.x, pos.y, pos.w, pos.h)
      alert(n > 1 ? `Pronto. Apaguei também ${n - 1} registro(s) iguais desse lugar.` : 'Pronto. Esse lugar será ignorado.')
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Não consegui marcar.')
    }
    await recarregar()
  }

  const cam = (id: string | null) => dados.cams.find((c) => c.id === id)
  const avisos = montarAvisos(dados, cam)
  const reais = dados.banheiro.filter((e) => !exemplo(e))
  const ult24 = reais.filter((e) => Date.now() - new Date(e.visto_em).getTime() < 86400_000)
  const conta = (t: EventoBanheiro['tipo']) => ult24.filter((e) => e.tipo === t).length
  const nomePet = (id: string | null) => dados.pets.find((p) => p.id === id)?.nome
  const porPet = [...dados.pets.map((p) => ({ id: p.id as string | null, nome: p.nome })), { id: null, nome: 'Sem identificar' }]
    .map((q) => ({ nome: q.nome, xixi: ult24.filter((e) => e.pet_id === q.id && e.tipo === 'xixi').length, coco: ult24.filter((e) => e.pet_id === q.id && e.tipo === 'coco').length, agua: ult24.filter((e) => e.pet_id === q.id && e.tipo === 'agua').length }))
    .filter((q) => q.xixi + q.coco + q.agua > 0)
  const linhaEvento = (e: EventoBanheiro) => (
    <li key={e.id} className="flex items-center gap-3 py-2">
      {e.snapshot_path && dados.fotos[e.snapshot_path] ? (
        <button type="button" className="shrink-0" onClick={() => abrir([{ id: e.id, url: dados.fotos[e.snapshot_path!], titulo: textoEvento(e, nomePet(e.pet_id)), legenda: `${cam(e.camera_id)?.nome ?? ''} · ${dataHora(e.visto_em)}` }])} aria-label="Ver foto">
          <img src={dados.fotos[e.snapshot_path]} alt="" className="h-12 w-20 rounded-xl object-cover" />
        </button>
      ) : (
        <span className="h-12 w-20 shrink-0 rounded-xl bg-slate-100" />
      )}
      <div className="min-w-0 flex-1">
        <p className="text-[13px] font-semibold text-slate-900">{textoEvento(e, nomePet(e.pet_id))}</p>
        <p className="text-[12px] text-slate-500">
          {dataHora(e.visto_em)} · {cam(e.camera_id)?.nome ?? ''}
        </p>
      </div>
    </li>
  )
  return (
    <div className="space-y-4">
      {janela}
      <button className="botao-principal w-full sm:w-auto" disabled={buscando} onClick={() => void localizar()}>
        <RefreshCw size={16} className={buscando ? 'animate-spin' : ''} /> {buscando ? 'Procurando nas câmeras…' : 'Onde estão agora?'}
      </button>
      <form
        className="vidro space-y-2 p-3"
        onSubmit={(e) => {
          e.preventDefault()
          if (texto.trim()) void comando()
        }}
      >
        <div className="flex gap-2">
          <input value={texto} onChange={(e) => setTexto(e.target.value)} placeholder={`Ex.: ${dados.pets[0]?.nome ?? 'Mavi'} na ${dados.cams[0]?.nome ?? 'Sala'}  ·  xixi no Banheiro`} className="min-w-0 flex-1" disabled={comandando} />
          <button type="submit" className="botao-principal compacto shrink-0" disabled={comandando || !texto.trim()}>
            Identificar
          </button>
        </div>
        {resposta && <p className="text-[13px] text-slate-600">{resposta}</p>}
      </form>
      {avisos.length > 0 && (
        <div className="vidro space-y-2 p-3">
          <p className="text-[12px] font-semibold uppercase tracking-wide text-slate-500">Avisos</p>
          <ul className="space-y-1.5">
            {avisos.map((a, k) => (
              <li key={k} className="flex items-center gap-3 text-[13px] text-slate-800">
                {a.foto && dados.fotos[a.foto] ? (
                  <button type="button" className="shrink-0" onClick={() => abrir([{ id: `aviso-${k}`, url: dados.fotos[a.foto!], titulo: a.titulo ?? 'Aviso', legenda: a.quando ? `${a.titulo ?? ''} · ${dataHora(a.quando)}` : (a.titulo ?? '') }])} aria-label="Ver foto">
                    <img src={dados.fotos[a.foto]} alt="" className="h-12 w-20 rounded-xl object-cover" />
                  </button>
                ) : (
                  <span className={`h-2 w-2 shrink-0 rounded-full ${a.tom === 'alerta' ? 'bg-amber-500' : a.tom === 'erro' ? 'bg-rose-500' : 'bg-emerald-500'}`} />
                )}
                <span className="min-w-0 flex-1">{a.texto}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <section className="vidro space-y-2 p-4">
        <h2 className="font-bold text-slate-900">Banheiro · últimas 24 h</h2>
        <div className="grid grid-cols-4 gap-2 text-center">
          {[
            ['Xixi', conta('xixi')],
            ['Cocô', conta('coco')],
            ['Limpezas', conta('limpo')],
            ['Água', conta('agua')],
          ].map(([nome, n]) => (
            <div key={nome as string} className="rounded-2xl bg-white/60 px-1 py-2">
              <p className="text-xl font-extrabold text-cyan-800">{n}</p>
              <p className="text-[11px] text-slate-600">{nome}</p>
            </div>
          ))}
        </div>
        {porPet.length > 0 && (
          <ul className="space-y-0.5 text-[12px] text-slate-600">
            {porPet.map((q) => (
              <li key={q.nome}>
                <strong className="text-slate-900">{q.nome}</strong>: {q.xixi} xixi · {q.coco} cocô · {q.agua} água
              </li>
            ))}
          </ul>
        )}
      </section>
      <section className="vidro p-4">
        <h2 className="font-bold text-slate-900">Eventos do banheiro</h2>
        {reais.length === 0 ? (
          <p className="pt-1 text-sm text-slate-500">Nenhum evento ainda.</p>
        ) : (
          <>
            <ul className="divide-y divide-slate-200/70">{(verTodos ? reais.slice(0, 20) : reais.slice(0, 1)).map(linhaEvento)}</ul>
            {reais.length > 1 && (
              <button className="mt-1 text-[12px] font-semibold text-cyan-800" onClick={() => setVerTodos(!verTodos)}>
                {verTodos ? 'Recolher' : `Ver anteriores (${Math.min(reais.length, 20) - 1})`}
              </button>
            )}
          </>
        )}
      </section>
      <div className="grid gap-4 sm:grid-cols-2">
        {dados.pets.map((pet) => {
          const pos = dados.pos.find((p) => p.pet_id === pet.id)
          const c = cam(pos?.camera_id ?? null)
          const recente = minutosDesde(pos?.visto_em) < 2
          const Icone = pet.especie === 'gato' ? Cat : Dog
          return (
            <article key={pet.id} className="vidro overflow-hidden">
              <div className="flex items-center gap-3 p-4">
                {pet.foto_perfil_path && dados.perfis[pet.foto_perfil_path] ? (
                  <img src={dados.perfis[pet.foto_perfil_path]} alt={pet.nome} className="h-11 w-11 rounded-2xl object-cover" />
                ) : (
                  <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-cyan-700/10 text-cyan-800">
                    <Icone size={22} strokeWidth={1.9} />
                  </span>
                )}
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
              {pos && (
                <div className="flex items-center gap-3 px-4 pb-3">
                  {pos.snapshot_path && dados.fotos[pos.snapshot_path] && (
                    <button type="button" className="shrink-0" onClick={() => abrir([{ id: pet.id, url: dados.fotos[pos.snapshot_path!], titulo: pet.nome, legenda: `${c?.nome ?? 'Câmera'} · foto de ${dataHora(pos.foto_em ?? pos.visto_em)}` }])} aria-label={`Ver foto de ${pet.nome}`}>
                      <img src={dados.fotos[pos.snapshot_path]} alt={`${pet.nome} na última posição`} className="h-16 w-28 rounded-xl object-cover" />
                    </button>
                  )}
                  <div className="min-w-0 flex-1 text-[12px] text-slate-500">
                    <p>Vista {haQuanto(pos.visto_em)}</p>
                    <p>Foto de {dataHora(pos.foto_em ?? pos.visto_em)}</p>
                    {admin && (
                      <button className="mt-1 font-semibold text-rose-600" onClick={() => void naoEPet(pos)}>
                        Não é ela
                      </button>
                    )}
                  </div>
                </div>
              )}
            </article>
          )
        })}
      </div>
      {secaoPessoas}
      {dados.desconhecidos > 0 && (
        <p className="vidro px-4 py-3 text-[12px] text-slate-600">
          {dados.desconhecidos} avistamento(s) de animal sem identificação na última hora. Veja no Histórico.
        </p>
      )}
    </div>
  )
}
