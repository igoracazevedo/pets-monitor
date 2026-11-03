import { useState } from 'react'
import { Camera as CamIcon, Check, Pencil } from 'lucide-react'
import { supabase, urlsDasFotos, type Camera } from '../lib/supabase'
import { useDados } from '../lib/dados'
import { haQuanto, minutosDesde } from '../lib/util'

const horaCompleta = (iso: string) => new Date(iso).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' })

export default function Cameras({ admin }: { admin: boolean }) {
  const [editando, setEditando] = useState<string | null>(null)
  const [apelido, setApelido] = useState('')
  const [msg, setMsg] = useState('')
  const [buscando, setBuscando] = useState(false)
  const { dados, erro, carregando, recarregar } = useDados<{ cams: Camera[]; fotos: Record<string, string> }>(
    async () => {
      const { data, error } = await supabase.from('pm_cameras').select('*').order('ordem').order('nome')
      if (error) throw new Error(error.message)
      const cams = (data ?? []) as Camera[]
      return { cams, fotos: await urlsDasFotos(cams.map((c) => c.ultimo_quadro_path)) }
    },
    { cams: [], fotos: {} },
    15000,
  )

  // "Ver ao vivo": pede ao programa de casa uma foto nova de cada câmera e mostra a hora de cada captura
  async function verAoVivo() {
    setBuscando(true)
    setMsg('')
    try {
      const { data, error } = await supabase.from('pm_pedidos').insert({ tipo: 'fotos' }).select('id').single()
      if (error || !data) throw error ?? new Error('não consegui enviar o pedido')
      let atendido = false
      for (let i = 0; i < 20 && !atendido; i++) {
        await new Promise((r) => setTimeout(r, 2000))
        const { data: p } = await supabase.from('pm_pedidos').select('atendido_em').eq('id', data.id).single()
        atendido = !!p?.atendido_em
      }
      if (!atendido) setMsg('O programa de casa não respondeu. Confira se o iniciar.bat está aberto no PC.')
      await recarregar()
    } catch (e) {
      setMsg(e instanceof Error ? e.message : (e as { message?: string })?.message ?? String(e))
    } finally {
      setBuscando(false)
    }
  }

  async function salvarApelido(id: string) {
    const nome = apelido.trim()
    if (!nome) return setEditando(null)
    const { error } = await supabase.from('pm_cameras').update({ nome }).eq('id', id)
    setMsg(error ? (error.message.includes('duplicate') ? 'Já existe uma câmera com esse nome.' : error.message) : '')
    if (!error) setEditando(null)
    await recarregar()
  }

  if (carregando) return <p className="p-6 text-center text-slate-500">Carregando…</p>
  if (erro) return <p className="p-6 text-center text-rose-600">{erro}</p>
  const visiveis = dados.cams.filter((c) => c.ativo)
  const ocultas = dados.cams.length - visiveis.length
  if (dados.cams.length === 0) return <p className="vidro p-6 text-center text-slate-500">As câmeras aparecem aqui assim que o programa de casa rodar a primeira varredura.</p>
  return (
    <div className="space-y-3">
      <button className="pilula" disabled={buscando} onClick={() => void verAoVivo()}>
        <CamIcon size={16} className={buscando ? 'animate-pulse' : ''} /> {buscando ? 'Tirando fotos…' : 'Ver ao vivo'}
      </button>
      {msg && <p className="text-sm text-rose-600">{msg}</p>}
      {admin && visiveis.some((c) => c.nome.startsWith('Câmera ')) && (
        <p className="vidro px-3 py-2 text-[12px] text-slate-600">Câmeras novas foram achadas na rede. Olhe a imagem e toque no lápis para dar o nome do local (Cozinha, Quarto…).</p>
      )}
      {ocultas > 0 && <p className="text-[12px] text-slate-500">{ocultas} câmera(s) desativada(s) — reative em Ajustes.</p>}
      <div className="grid gap-4 sm:grid-cols-2">
        {visiveis.map((c) => {
          const fora = c.ultimo_status === 'erro' || minutosDesde(c.ultima_leitura) > 5
          const base = c.ultimo_quadro_path ? dados.fotos[c.ultimo_quadro_path] : undefined
          const img = base ? `${base}${base.includes('?') ? '&' : '?'}t=${c.foto_em ? Date.parse(c.foto_em) : 0}` : undefined
          return (
            <article key={c.id} className={`vidro overflow-hidden ${c.ativo ? '' : 'opacity-60'}`}>
              {img ? <img src={img} alt={c.nome} className="aspect-video w-full object-cover" /> : <div className="flex aspect-video items-center justify-center bg-slate-100 text-slate-400">sem imagem</div>}
              <div className="flex items-center justify-between gap-2 p-3">
                <div className="min-w-0 flex-1">
                  {editando === c.id ? (
                    <form className="flex items-center gap-1" onSubmit={(e) => { e.preventDefault(); void salvarApelido(c.id) }}>
                      <input autoFocus value={apelido} onChange={(e) => setApelido(e.target.value)} className="min-w-0 flex-1" placeholder="Ex.: Cozinha" />
                      <button className="pilula" aria-label="Salvar nome"><Check size={16} /></button>
                    </form>
                  ) : (
                    <h2 className="flex items-center gap-1.5 font-bold text-slate-900">
                      <span className="truncate">{c.nome}</span>
                      {admin && (
                        <button type="button" aria-label="Renomear câmera" className="shrink-0 text-slate-400" onClick={() => { setEditando(c.id); setApelido(c.nome.startsWith('Câmera ') ? '' : c.nome) }}>
                          <Pencil size={13} />
                        </button>
                      )}
                    </h2>
                  )}
                  <p className="truncate text-[12px] text-slate-500">
                    {c.ip_atual ? `${c.ip_atual} · ` : ''}
                    {c.foto_em ? `Foto de ${horaCompleta(c.foto_em)} (${haQuanto(c.foto_em)})` : 'Sem foto ainda'}
                  </p>
                  {c.ultimo_erro && fora && <p className="truncate text-[11px] text-rose-600">{c.ultimo_erro}</p>}
                </div>
                <span className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] font-bold ${fora ? 'bg-rose-100 text-rose-700' : 'bg-emerald-100 text-emerald-700'}`}>{fora ? 'Sem sinal' : 'Online'}</span>
              </div>
            </article>
          )
        })}
      </div>
    </div>
  )
}
