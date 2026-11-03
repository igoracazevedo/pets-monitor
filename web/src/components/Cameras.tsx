import { useEffect, useState } from 'react'
import { Radio } from 'lucide-react'
import { supabase, urlsDasFotos, type Camera } from '../lib/supabase'
import { useDados } from '../lib/dados'
import { haQuanto, minutosDesde } from '../lib/util'

// Mesmo critério do agente: nome da câmera vira nome de arquivo sem acento/símbolo
const slug = (n: string) => n.normalize('NFKD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-zA-Z0-9]+/g, '-').replace(/^-+|-+$/g, '').toLowerCase() || 'camera'

export default function Cameras() {
  const [aoVivo, setAoVivo] = useState(false)
  const [tic, setTic] = useState(0)
  const [vivas, setVivas] = useState<Record<string, string>>({})
  const { dados, erro, carregando } = useDados<{ cams: Camera[]; fotos: Record<string, string> }>(
    async () => {
      const { data, error } = await supabase.from('pm_cameras').select('*').order('ordem').order('nome')
      if (error) throw new Error(error.message)
      const cams = (data ?? []) as Camera[]
      return { cams, fotos: await urlsDasFotos(cams.map((c) => c.ultimo_quadro_path)) }
    },
    { cams: [], fotos: {} },
    aoVivo ? 3600_000 : 15000,
  )

  // Ao vivo: avisa o programa de casa (a cada 15 s) e recarrega as imagens a cada 2 s
  useEffect(() => {
    if (!aoVivo) return
    let ativo = true
    const aviso = () => void supabase.from('pm_ao_vivo').update({ ate: new Date(Date.now() + 40_000).toISOString() }).eq('id', 1)
    aviso()
    void urlsDasFotos(dados.cams.map((c) => `ao-vivo/${slug(c.nome)}.jpg`)).then((u) => ativo && setVivas(u))
    const a = setInterval(aviso, 15000)
    const b = setInterval(() => setTic((t) => t + 1), 2000)
    return () => {
      ativo = false
      clearInterval(a)
      clearInterval(b)
      void supabase.from('pm_ao_vivo').update({ ate: new Date().toISOString() }).eq('id', 1)
    }
  }, [aoVivo, dados.cams])

  if (carregando) return <p className="p-6 text-center text-slate-500">Carregando…</p>
  if (erro) return <p className="p-6 text-center text-rose-600">{erro}</p>
  if (dados.cams.length === 0) return <p className="vidro p-6 text-center text-slate-500">As câmeras aparecem aqui assim que o programa de casa rodar a primeira varredura.</p>
  return (
    <div className="space-y-3">
      <button className={`pilula ${aoVivo ? 'bg-rose-600' : ''}`} onClick={() => setAoVivo((v) => !v)}>
        <Radio size={16} /> {aoVivo ? 'Parar ao vivo' : 'Ver ao vivo'}
      </button>
      {aoVivo && <p className="text-[12px] text-slate-500">Atualiza a cada poucos segundos. Pode levar alguns segundos para a primeira imagem aparecer.</p>}
      <div className="grid gap-4 sm:grid-cols-2">
        {dados.cams.map((c) => {
          const fora = c.ultimo_status === 'erro' || minutosDesde(c.ultima_leitura) > 5
          const viva = aoVivo ? vivas[`ao-vivo/${slug(c.nome)}.jpg`] : undefined
          const img = viva ? `${viva}&t=${tic}` : c.ultimo_quadro_path ? dados.fotos[c.ultimo_quadro_path] : undefined
          return (
            <article key={c.id} className={`vidro overflow-hidden ${c.ativo ? '' : 'opacity-60'}`}>
              {img ? <img src={img} alt={c.nome} className="aspect-video w-full object-cover" /> : <div className="flex aspect-video items-center justify-center bg-slate-100 text-slate-400">sem imagem</div>}
              <div className="flex items-center justify-between gap-2 p-3">
                <div className="min-w-0">
                  <h2 className="truncate font-bold text-slate-900">{c.nome}</h2>
                  <p className="truncate text-[12px] text-slate-500">{c.ambiente ?? 'sem ambiente'} · lida {haQuanto(c.ultima_leitura)}</p>
                  {c.ultimo_erro && <p className="truncate text-[11px] text-rose-600">{c.ultimo_erro}</p>}
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
