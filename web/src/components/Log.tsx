import { useEffect, useMemo, useRef, useState } from 'react'
import { supabase } from '../lib/supabase'
import { useDados } from '../lib/dados'

type Linha = { id: number; created_at: string; nivel: string; linha: string }

const QUANTAS = 400

function hora(iso: string) {
  return new Date(iso).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function ha(iso: string) {
  const s = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000))
  if (s < 90) return `${s} s`
  if (s < 5400) return `${Math.round(s / 60)} min`
  return `${Math.round(s / 3600)} h`
}

/** Espelho da janela do iniciar.bat: o programa de casa envia cada linha para o banco e aqui ela aparece em poucos segundos. */
export default function Log() {
  const [soErros, setSoErros] = useState(false)
  const [pausado, setPausado] = useState(false)
  const [busca, setBusca] = useState('')
  const [copiado, setCopiado] = useState(false)
  const fim = useRef<HTMLDivElement>(null)
  const caixa = useRef<HTMLDivElement>(null)
  const colado = useRef(true) // acompanha o fim enquanto a pessoa não rolar para cima

  const { dados, erro } = useDados<Linha[]>(
    async () => {
      if (pausado) return []
      const { data, error } = await supabase.from('pm_logs').select('id,created_at,nivel,linha').order('id', { ascending: false }).limit(QUANTAS)
      if (error) throw new Error(error.message)
      return ((data ?? []) as Linha[]).reverse()
    },
    [],
    3000,
  )
  // mantém a última leitura quando pausado (a carga devolve [] só para não consultar o banco)
  const ultima = useRef<Linha[]>([])
  if (!pausado) ultima.current = dados
  const linhas = ultima.current

  const visiveis = useMemo(() => {
    const b = busca.trim().toLowerCase()
    return linhas.filter((l) => (!soErros || l.nivel === 'erro') && (!b || l.linha.toLowerCase().includes(b)))
  }, [linhas, soErros, busca])

  useEffect(() => {
    if (colado.current) fim.current?.scrollIntoView({ block: 'end' })
  }, [visiveis])

  function aoRolar() {
    const c = caixa.current
    if (c) colado.current = c.scrollHeight - c.scrollTop - c.clientHeight < 40
  }

  async function copiar() {
    try {
      await navigator.clipboard.writeText(visiveis.map((l) => `${hora(l.created_at)} ${l.linha}`).join('\n'))
      setCopiado(true)
      setTimeout(() => setCopiado(false), 1500)
    } catch {
      /* sem permissão da área de transferência */
    }
  }

  const ultimaLinha = linhas[linhas.length - 1]
  const parado = ultimaLinha ? Date.now() - new Date(ultimaLinha.created_at).getTime() > 7 * 60 * 1000 : false

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-[12px] font-semibold ${!ultimaLinha ? 'bg-slate-100 text-slate-500' : parado ? 'bg-amber-100 text-amber-800' : 'bg-emerald-100 text-emerald-800'}`}>
          <span className={`h-2 w-2 rounded-full ${!ultimaLinha ? 'bg-slate-400' : parado ? 'bg-amber-500' : 'bg-emerald-500'}`} />
          {!ultimaLinha ? 'Sem registros' : parado ? `Sem sinal há ${ha(ultimaLinha.created_at)}` : `Ativo · última linha há ${ha(ultimaLinha.created_at)}`}
        </span>
        <div className="ml-auto flex gap-2">
          <button className={`rounded-full px-3 py-1 text-[12px] font-semibold ring-1 ${soErros ? 'bg-rose-600 text-white ring-rose-600' : 'bg-white text-slate-600 ring-slate-200'}`} onClick={() => setSoErros(!soErros)}>
            Só erros
          </button>
          <button className={`rounded-full px-3 py-1 text-[12px] font-semibold ring-1 ${pausado ? 'bg-amber-500 text-white ring-amber-500' : 'bg-white text-slate-600 ring-slate-200'}`} onClick={() => setPausado(!pausado)}>
            {pausado ? 'Retomar' : 'Pausar'}
          </button>
          <button className="rounded-full bg-white px-3 py-1 text-[12px] font-semibold text-slate-600 ring-1 ring-slate-200" onClick={() => void copiar()}>
            {copiado ? 'Copiado' : 'Copiar'}
          </button>
        </div>
      </div>

      <input
        value={busca}
        onChange={(e) => setBusca(e.target.value)}
        placeholder="Filtrar (ex.: Banheiro, erro, Mavi)"
        className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-[14px] outline-none focus:border-[#0e7490]"
      />

      {erro && (
        <p className="rounded-xl bg-rose-50 px-3 py-2 text-[13px] text-rose-700">
          {erro.includes('pm_logs') ? 'A tabela do log ainda não existe: rode o trecho SQL do log no Supabase.' : erro}
        </p>
      )}

      <div ref={caixa} onScroll={aoRolar} className="h-[60vh] overflow-auto rounded-2xl bg-slate-900 p-3 font-mono text-[11.5px] leading-[1.45] text-slate-200">
        {visiveis.length === 0 && !erro && (
          <p className="text-slate-400">{linhas.length === 0 ? 'Nenhuma linha ainda. Abra o iniciar.bat (versão atualizada) e aguarde alguns segundos.' : 'Nada com esse filtro.'}</p>
        )}
        {visiveis.map((l) => (
          <div key={l.id} className={`flex gap-2 py-px ${l.nivel === 'erro' ? 'text-rose-300' : ''}`}>
            <span className="shrink-0 text-slate-500">{hora(l.created_at)}</span>
            <span className="min-w-0 whitespace-pre-wrap break-words">{l.linha}</span>
          </div>
        ))}
        <div ref={fim} />
      </div>
      <p className="text-center text-[11px] text-slate-400">Últimas {QUANTAS} linhas · atualiza a cada 3 s · guarda 3 dias</p>
    </div>
  )
}
