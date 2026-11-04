import { useState } from 'react'
import { Cat, Dog, RefreshCw, Users } from 'lucide-react'
import { marcarComoObjeto, supabase, urlsDasFotos, urlsDosPets, type Camera, type EventoBanheiro, type Pet, type Posicao, type Presenca } from '../lib/supabase'
import { useDados } from '../lib/dados'
import { useVisualizador } from './Visualizador'
import { dataHora, haQuanto, minutosDesde } from '../lib/util'
import { textoEvento } from '../lib/eventos'

type Dados = { pets: Pet[]; pos: Posicao[]; cams: Camera[]; fotos: Record<string, string>; perfis: Record<string, string>; desconhecidos: number; gente: Presenca[]; banheiro: EventoBanheiro[] }

/** Fotos que ilustram os avisos: a mais recente de cada câmera do banheiro e o último quadro das câmeras sem sinal. */
function fotosDosAvisos(ev: EventoBanheiro[], cams: Camera[]): (string | null)[] {
  const ultimas = new Map<string, string>()
  for (const e of ev) if (e.snapshot_path && !ultimas.has(`${e.camera_id}|${e.tipo}`)) ultimas.set(`${e.camera_id}|${e.tipo}`, e.snapshot_path)
  const quadros = cams.filter((c) => c.ultimo_quadro_path && (c.ultimo_status === 'erro' || ev.some((e) => e.camera_id === c.id))).map((c) => c.ultimo_quadro_path)
  const recentes = ev.slice(0, 20).map((e) => e.snapshot_path)
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
  const ultimo = d.banheiro[0]
  if (ultimo) {
    const quem = d.pets.find((p) => p.id === ultimo.pet_id)?.nome
    out.push({ texto: `Último evento: ${textoEvento(ultimo, quem)} em ${dataHora(ultimo.visto_em)}.`, tom: 'ok', foto: ultimo.snapshot_path, quando: ultimo.visto_em, titulo: textoEvento(ultimo, quem) })
  }
  const porCamera = new Map<string, EventoBanheiro[]>()
  for (const e of d.banheiro.filter((x) => x.tipo !== 'agua' && x.tipo !== 'comeu')) porCamera.set(e.camera_id, [...(porCamera.get(e.camera_id) ?? []), e])
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

const NEGACAO = /\b(nao|sem|nenhum|nenhuma|nada|nem|nunca)\b/

/** "coco no Banheiro" ensina coco; "não tem coco" / "sem xixi" é negação e ensina "limpo" (senão a IA aprenderia o contrário do que foi escrito). */
function rotuloDoTexto(t: string): { rotulo?: 'xixi' | 'coco' | 'limpo'; negou?: string; duvida?: boolean } {
  const achados = (['xixi', 'coco', 'limpo'] as const).flatMap((r) => {
    const m = new RegExp(`\\b${r}\\b`).exec(t)
    if (!m) return []
    const antes = t.slice(0, m.index).split(/[,;.]| mas | so | apenas /).pop() ?? ''
    return [{ r, negado: NEGACAO.test(antes) }]
  })
  const positivo = achados.find((a) => !a.negado)
  if (positivo) return { rotulo: positivo.r }
  const sujeira = achados.filter((a) => a.negado && a.r !== 'limpo')
  if (sujeira.length) return { rotulo: 'limpo', negou: sujeira.map((a) => a.r).join(' nem ') }
  if (achados.some((a) => a.negado)) return { duvida: true } // "não está limpo": falta dizer o que tem
  return {}
}

export default function Inicio({ admin, onIr }: { admin: boolean; onIr?: (aba: string) => void }) {
  const [buscando, setBuscando] = useState(false)
  const [texto, setTexto] = useState('')
  const [comandando, setComandando] = useState(false)
  const [resposta, setResposta] = useState('')
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
  /** "Mavi bebeu água no Banheiro às 21:23": registra o evento à mão (usa a foto do Histórico dessa hora, se houver). */
  async function registrarAgua(t: string) {
    const pet = [...dados.pets].sort((a, b) => b.nome.length - a.nome.length).find((p) => t.includes(sem(p.nome)))
    const bs = dados.cams.filter((c) => sem(c.nome).includes('banheiro'))
    const cam = [...dados.cams].sort((a, b) => b.nome.length - a.nome.length).find((c) => t.includes(sem(c.nome))) ?? (bs.length === 1 ? bs[0] : undefined)
    if (!pet || !cam) {
      setResposta(`Não entendi. Escreva, por exemplo: "${dados.pets[0]?.nome ?? 'Mavi'} bebeu água no ${bs[0]?.nome ?? 'Banheiro'} às 21:23".`)
      return
    }
    const quando = new Date()
    const h = t.match(/(\d{1,2})\s*[:h]\s*(\d{2})/)
    if (h) {
      quando.setHours(Number(h[1]), Number(h[2]), 0, 0)
      if (quando.getTime() > Date.now() + 60_000) quando.setDate(quando.getDate() - 1)
    }
    setComandando(true)
    try {
      const ini = new Date(quando.getTime() - 10 * 60_000).toISOString()
      const fim = new Date(quando.getTime() + 10 * 60_000).toISOString()
      const { data: av } = await supabase.from('pm_avistamentos').select('snapshot_path,visto_em,pet_id').eq('camera_id', cam.id).gte('visto_em', ini).lte('visto_em', fim).not('snapshot_path', 'is', null)
      const perto = ((av ?? []) as { snapshot_path: string; visto_em: string; pet_id: string | null }[]).sort((a, b) => Number(b.pet_id === pet.id) - Number(a.pet_id === pet.id) || Math.abs(Date.parse(a.visto_em) - quando.getTime()) - Math.abs(Date.parse(b.visto_em) - quando.getTime()))[0]
      const { error } = await supabase.from('pm_banheiro_eventos').insert({ camera_id: cam.id, tipo: 'agua', pet_id: pet.id, snapshot_path: perto?.snapshot_path ?? null, visto_em: quando.toISOString() })
      if (error) throw error
      setResposta(`Registrado: ${pet.nome} bebeu água em ${cam.nome} às ${dataHora(quando.toISOString())}${perto ? ' (com a foto do Histórico dessa hora)' : ' (sem foto: não havia registro nessa hora)'}.`)
      setTexto('')
      await recarregar()
    } catch (e) {
      setResposta(e instanceof Error ? e.message : (e as { message?: string })?.message ?? 'Não consegui registrar. Rode o SQL do evento "agua" no Supabase.')
    } finally {
      setComandando(false)
    }
  }
  /** Linha de comando: "Mavi na Sala" -> o programa de casa tira a foto de agora da câmera, marca o pet e aprende com ela. */
  async function comando() {
    const t = sem(texto)
    if (/beb(eu|endo|er)\s+agua/.test(t)) {
      await registrarAgua(t)
      return
    }
    const { rotulo, negou, duvida } = rotuloDoTexto(t)
    if (duvida) {
      setResposta('Entendi que o tapete não está limpo. Está com xixi ou com coco? Escreva, por exemplo: "coco no Banheiro".')
      return
    }
    if (rotulo) {
      const bs = dados.cams.filter((c) => sem(c.nome).includes('banheiro'))
      const cam = [...dados.cams].sort((a, b) => b.nome.length - a.nome.length).find((c) => t.includes(sem(c.nome))) ?? (bs.length === 1 ? bs[0] : undefined)
      if (!cam) {
        setResposta(`Qual câmera? Escreva, por exemplo: "${rotulo} no ${bs[0]?.nome ?? 'Banheiro'}".`)
        return
      }
      await pedir({ tipo: 'ensinar_banheiro', camera_id: cam.id, rotulo }, negou ? `Entendi que não tem ${negou}: ensinando "limpo" na câmera ${cam.nome}…` : `Ensinando "${rotulo}" na câmera ${cam.nome}…`)
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
  const avisos = montarAvisos(dados, cam).slice(0, 1) // só o aviso mais recente; o resto fica no menu Eventos
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
          {onIr && (
            <button className="text-[12px] font-semibold text-cyan-800" onClick={() => onIr('eventos')}>
              Ver todos os eventos e gráficos →
            </button>
          )}
        </div>
      )}
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
