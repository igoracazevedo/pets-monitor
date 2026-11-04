import { useMemo, useState } from 'react'
import { supabase, urlsDasFotos, type Camera, type EventoBanheiro, type Pet } from '../lib/supabase'
import { useDados } from '../lib/dados'
import { dataHora } from '../lib/util'
import { exemplo, SERIES, textoEvento } from '../lib/eventos'
import { useVisualizador } from './Visualizador'

type Dados = { eventos: EventoBanheiro[]; pets: Pet[]; cams: Camera[]; fotos: Record<string, string> }
type Periodo = '24h' | '7d' | '30d'
type Balde = { rotulo: string; contagem: Record<string, number>; total: number }

const PERIODOS: { id: Periodo; nome: string; ms: number }[] = [
  { id: '24h', nome: '24 horas', ms: 86400_000 },
  { id: '7d', nome: '7 dias', ms: 7 * 86400_000 },
  { id: '30d', nome: '30 dias', ms: 30 * 86400_000 },
]
const TINTA = { forte: '#0b0b0b', suave: '#52514e', grade: '#e4e2dd', superficie: '#ffffff' }

const vazio = () => Object.fromEntries(SERIES.map((s) => [s.id, 0])) as Record<string, number>
function baldes(ev: EventoBanheiro[], n: number, chave: (d: Date) => number, rotulo: (i: number) => string): Balde[] {
  const b: Balde[] = Array.from({ length: n }, (_, i) => ({ rotulo: rotulo(i), contagem: vazio(), total: 0 }))
  for (const e of ev) {
    const i = chave(new Date(e.visto_em))
    if (i >= 0 && i < n) {
      b[i].contagem[e.tipo]++
      b[i].total++
    }
  }
  return b
}
const bonito = (max: number) => {
  const passo = max <= 5 ? 1 : max <= 10 ? 2 : max <= 25 ? 5 : 10
  return Math.max(passo, Math.ceil(max / passo) * passo)
}

/** Colunas empilhadas por tipo. Barra até 24 px, vão de 2 px entre as partes, ponta de cima arredondada. */
export function Colunas({ dados, passoRotulo, titulo }: { dados: Balde[]; passoRotulo: number; titulo: string }) {
  const [sobre, setSobre] = useState<number | null>(null)
  const W = 640, H = 220, ML = 34, MB = 28, MT = 10
  const topo = bonito(Math.max(1, ...dados.map((d) => d.total)))
  const fatia = (W - ML - 6) / dados.length
  const larg = Math.min(24, fatia * 0.62)
  const y = (v: number) => MT + (H - MT - MB) * (1 - v / topo)
  const ticks = [0, topo / 2, topo].filter((v, i, a) => Number.isInteger(v) && a.indexOf(v) === i)
  const d = sobre != null ? dados[sobre] : null
  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={titulo} className="w-full">
        {ticks.map((t) => (
          <g key={t}>
            <line x1={ML} x2={W} y1={y(t)} y2={y(t)} stroke={TINTA.grade} strokeWidth={1} />
            <text x={ML - 6} y={y(t) + 4} textAnchor="end" fontSize={16} fill={TINTA.suave}>{t}</text>
          </g>
        ))}
        {dados.map((b, i) => {
          const cx = ML + fatia * i + fatia / 2
          let base = 0
          const partes = SERIES.filter((s) => b.contagem[s.id] > 0)
          return (
            <g key={i}>
              {partes.map((s, k) => {
                const v = b.contagem[s.id]
                const y0 = y(base), y1 = y(base + v)
                base += v
                const alt = Math.max(0, y0 - y1 - (k < partes.length - 1 ? 2 : 0)) // 2 px de vão entre as partes
                const ultimo = k === partes.length - 1
                const r = ultimo ? Math.min(4, larg / 2, alt) : 0
                const x = cx - larg / 2, yt = y1 + (ultimo ? 0 : 2)
                const caminho = `M${x},${yt + alt} V${yt + r} Q${x},${yt} ${x + r},${yt} H${x + larg - r} Q${x + larg},${yt} ${x + larg},${yt + r} V${yt + alt} Z`
                return <path key={s.id} d={caminho} fill={s.cor} opacity={sobre == null || sobre === i ? 1 : 0.55} />
              })}
              {i % passoRotulo === 0 && <text x={cx} y={H - 7} textAnchor="middle" fontSize={16} fill={TINTA.suave}>{b.rotulo}</text>}
              <rect x={cx - fatia / 2} y={MT} width={fatia} height={H - MT - MB} fill="transparent" tabIndex={0} aria-label={`${b.rotulo}: ${b.total} evento(s)`} onPointerEnter={() => setSobre(i)} onPointerLeave={() => setSobre(null)} onFocus={() => setSobre(i)} onBlur={() => setSobre(null)} />
            </g>
          )
        })}
      </svg>
      {d && sobre != null && (
        <div className="pointer-events-none absolute -top-1 z-10 rounded-xl bg-white px-3 py-2 text-[12px] shadow-lg ring-1 ring-slate-200" style={{ left: `${Math.min(70, Math.max(0, ((ML + fatia * sobre) / W) * 100 - 8))}%` }}>
          <p className="font-semibold" style={{ color: TINTA.forte }}>{d.rotulo}</p>
          {SERIES.map((s) => (
            <p key={s.id} className="flex items-center gap-2" style={{ color: TINTA.suave }}>
              <span className="inline-block h-[3px] w-3 rounded" style={{ background: s.cor }} />
              <strong style={{ color: TINTA.forte }}>{d.contagem[s.id]}</strong> {s.nome}
            </p>
          ))}
        </div>
      )}
    </div>
  )
}

/** Uma barra horizontal por cachorra, empilhada por tipo. */
export function BarrasPorPet({ linhas }: { linhas: { nome: string; contagem: Record<string, number>; total: number }[] }) {
  const max = bonito(Math.max(1, ...linhas.map((l) => l.total)))
  return (
    <ul className="space-y-2">
      {linhas.map((l) => (
        <li key={l.nome} className="flex items-center gap-3 text-[12px]">
          <span className="w-24 shrink-0 truncate font-semibold" style={{ color: TINTA.forte }}>{l.nome}</span>
          <div className="flex h-5 flex-1 items-center" role="img" aria-label={`${l.nome}: ${SERIES.map((s) => `${l.contagem[s.id]} ${s.nome}`).join(', ')}`}>
            <div className="flex h-5 gap-[2px]" style={{ width: `${(l.total / max) * 100}%` }}>
              {SERIES.filter((s) => l.contagem[s.id] > 0).map((s, k, a) => (
                <div key={s.id} title={`${s.nome}: ${l.contagem[s.id]}`} style={{ flex: l.contagem[s.id], background: s.cor, borderRadius: k === a.length - 1 ? '0 4px 4px 0' : 0 }} />
              ))}
            </div>
          </div>
          <span className="w-6 shrink-0 text-right font-bold" style={{ color: TINTA.forte }}>{l.total}</span>
        </li>
      ))}
    </ul>
  )
}

export const Legenda = () => (
  <div className="flex flex-wrap gap-x-4 gap-y-1 text-[12px]" style={{ color: TINTA.suave }}>
    {SERIES.map((s) => (
      <span key={s.id} className="flex items-center gap-1.5">
        <span className="inline-block h-3 w-3 rounded-[3px]" style={{ background: s.cor }} />
        {s.nome}
      </span>
    ))}
  </div>
)

function Tabela({ cab, linhas }: { cab: string; linhas: Balde[] }) {
  return (
    <div className="max-h-56 overflow-auto rounded-xl bg-white/60">
      <table className="w-full text-[12px]">
        <thead>
          <tr className="text-left" style={{ color: TINTA.suave }}>
            <th className="p-2">{cab}</th>
            {SERIES.map((s) => <th key={s.id} className="p-2 text-right">{s.nome}</th>)}
          </tr>
        </thead>
        <tbody>
          {linhas.filter((l) => l.total > 0).map((l) => (
            <tr key={l.rotulo} className="border-t border-slate-200/70">
              <td className="p-2 font-semibold">{l.rotulo}</td>
              {SERIES.map((s) => <td key={s.id} className="p-2 text-right">{l.contagem[s.id]}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function Eventos() {
  const [periodo, setPeriodo] = useState<Periodo>('7d')
  const [tipo, setTipo] = useState<'todos' | EventoBanheiro['tipo']>('todos')
  const [pet, setPet] = useState('todos')
  const [tabela, setTabela] = useState(false)
  const [quantos, setQuantos] = useState(20)
  const { abrir, janela } = useVisualizador()
  const { dados, erro, carregando } = useDados<Dados>(
    async () => {
      const [ev, pets, cams] = await Promise.all([
        supabase.from('pm_banheiro_eventos').select('*').gte('visto_em', new Date(Date.now() - 30 * 86400_000).toISOString()).order('visto_em', { ascending: false }).limit(2000),
        supabase.from('pm_pets').select('*').order('nome'),
        supabase.from('pm_cameras').select('*'),
      ])
      if (ev.error) throw new Error(ev.error.message)
      const eventos = ((ev.data ?? []) as EventoBanheiro[]).filter((e) => !exemplo(e))
      return { eventos, pets: (pets.data ?? []) as Pet[], cams: (cams.data ?? []) as Camera[], fotos: await urlsDasFotos(eventos.slice(0, 60).map((e) => e.snapshot_path)) }
    },
    { eventos: [], pets: [], cams: [], fotos: {} },
    30000,
  )
  const ms = PERIODOS.find((p) => p.id === periodo)!.ms
  const noPeriodo = useMemo(() => dados.eventos.filter((e) => Date.now() - new Date(e.visto_em).getTime() < ms), [dados.eventos, ms])
  const filtrados = noPeriodo.filter((e) => (tipo === 'todos' || e.tipo === tipo) && (pet === 'todos' || (pet === 'sem' ? !e.pet_id : e.pet_id === pet)))
  const nomePet = (id: string | null) => dados.pets.find((p) => p.id === id)?.nome

  const agora = new Date()
  const serie = useMemo(() => {
    if (periodo === '24h') {
      const h0 = new Date(agora); h0.setMinutes(0, 0, 0)
      return { passo: 3, titulo: 'Eventos por hora (últimas 24 h)', cab: 'Hora', dados: baldes(filtrados, 24, (d) => 23 - Math.floor((h0.getTime() + 3600_000 - d.getTime()) / 3600_000), (i) => `${String((h0.getHours() - 23 + i + 48) % 24).padStart(2, '0')}h`) }
    }
    const n = periodo === '7d' ? 7 : 30
    const d0 = new Date(agora); d0.setHours(0, 0, 0, 0)
    return { passo: periodo === '7d' ? 1 : 5, titulo: `Eventos por dia (últimos ${n} dias)`, cab: 'Dia', dados: baldes(filtrados, n, (d) => { const x = new Date(d); x.setHours(0, 0, 0, 0); return n - 1 - Math.round((d0.getTime() - x.getTime()) / 86400_000) }, (i) => { const x = new Date(d0); x.setDate(x.getDate() - (n - 1 - i)); return x.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' }) }) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [periodo, filtrados])
  const porHora = useMemo(() => baldes(filtrados, 24, (d) => d.getHours(), (i) => `${String(i).padStart(2, '0')}h`), [filtrados])
  const porPet = [...dados.pets.map((p) => ({ id: p.id as string | null, nome: p.nome })), { id: null, nome: 'Sem identificar' }]
    .map((q) => {
      const c = vazio()
      for (const e of filtrados) if (e.pet_id === q.id) c[e.tipo]++
      return { nome: q.nome, contagem: c, total: Object.values(c).reduce((a, b) => a + b, 0) }
    })
    .filter((l) => l.total > 0)
  const conta = (t: EventoBanheiro['tipo']) => noPeriodo.filter((e) => e.tipo === t).length

  if (carregando) return <p className="p-6 text-center text-slate-500">Carregando…</p>
  if (erro) return <p className="p-6 text-center text-rose-600">{erro}</p>
  return (
    <div className="space-y-4">
      {janela}
      <div className="flex flex-wrap gap-2">
        <select value={periodo} onChange={(e) => setPeriodo(e.target.value as Periodo)} aria-label="Período">
          {PERIODOS.map((p) => <option key={p.id} value={p.id}>Últimas {p.nome}</option>)}
        </select>
        <select value={tipo} onChange={(e) => setTipo(e.target.value as typeof tipo)} aria-label="Tipo de evento">
          <option value="todos">Todos os eventos</option>
          {SERIES.map((s) => <option key={s.id} value={s.id}>{s.nome}</option>)}
        </select>
        <select value={pet} onChange={(e) => setPet(e.target.value)} aria-label="Cachorra">
          <option value="todos">Todas</option>
          {dados.pets.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
          <option value="sem">Sem identificar</option>
        </select>
      </div>

      <div className="grid grid-cols-4 gap-2 text-center">
        {SERIES.map((s) => (
          <div key={s.id} className="vidro px-1 py-3">
            <p className="text-2xl font-extrabold" style={{ color: TINTA.forte }}>{conta(s.id)}</p>
            <p className="flex items-center justify-center gap-1.5 text-[11px]" style={{ color: TINTA.suave }}>
              <span className="inline-block h-2.5 w-2.5 rounded-[3px]" style={{ background: s.cor }} />{s.nome}
            </p>
          </div>
        ))}
      </div>

      <section className="vidro space-y-3 p-4">
        <div className="flex items-center justify-between gap-2">
          <h2 className="font-bold text-slate-900">{serie.titulo}</h2>
          <button className="text-[12px] font-semibold text-cyan-800" onClick={() => setTabela(!tabela)}>{tabela ? 'Ver gráficos' : 'Ver como tabela'}</button>
        </div>
        <Legenda />
        {filtrados.length === 0 ? <p className="py-6 text-center text-sm text-slate-500">Nenhum evento nesse período.</p> : tabela ? <Tabela cab={serie.cab} linhas={serie.dados} /> : <Colunas dados={serie.dados} passoRotulo={serie.passo} titulo={serie.titulo} />}
      </section>

      {filtrados.length > 0 && !tabela && (
        <section className="vidro space-y-3 p-4">
          <h2 className="font-bold text-slate-900">Em que horas acontece</h2>
          <p className="text-[12px] text-slate-500">Soma de todos os dias do período, pela hora do dia.</p>
          <Colunas dados={porHora} passoRotulo={3} titulo="Eventos por hora do dia" />
        </section>
      )}

      {porPet.length > 0 && !tabela && (
        <section className="vidro space-y-3 p-4">
          <h2 className="font-bold text-slate-900">Por cachorra</h2>
          <BarrasPorPet linhas={porPet} />
        </section>
      )}

      <section className="vidro p-4">
        <h2 className="font-bold text-slate-900">Todos os eventos ({filtrados.length})</h2>
        {filtrados.length === 0 ? <p className="pt-1 text-sm text-slate-500">Nada por aqui.</p> : (
          <ul className="divide-y divide-slate-200/70">
            {filtrados.slice(0, quantos).map((e) => (
              <li key={e.id} className="flex items-center gap-3 py-2">
                {e.snapshot_path && dados.fotos[e.snapshot_path] ? (
                  <button type="button" className="shrink-0" onClick={() => abrir([{ id: e.id, url: dados.fotos[e.snapshot_path!], titulo: textoEvento(e, nomePet(e.pet_id)), legenda: `${dados.cams.find((c) => c.id === e.camera_id)?.nome ?? ''} · ${dataHora(e.visto_em)}` }])} aria-label="Ver foto">
                    <img src={dados.fotos[e.snapshot_path]} alt="" className="h-12 w-20 rounded-xl object-cover" loading="lazy" />
                  </button>
                ) : <span className="h-12 w-20 shrink-0 rounded-xl bg-slate-100" />}
                <div className="min-w-0 flex-1">
                  <p className="text-[13px] font-semibold text-slate-900">{textoEvento(e, nomePet(e.pet_id))}</p>
                  <p className="text-[12px] text-slate-500">{dataHora(e.visto_em)} · {dados.cams.find((c) => c.id === e.camera_id)?.nome ?? ''}</p>
                </div>
              </li>
            ))}
          </ul>
        )}
        {filtrados.length > quantos && <button className="mt-2 text-[12px] font-semibold text-cyan-800" onClick={() => setQuantos(quantos + 20)}>Ver mais</button>}
        <p className="pt-2 text-[11px] text-slate-400">As fotos aparecem para os 60 eventos mais recentes.</p>
      </section>
    </div>
  )
}
