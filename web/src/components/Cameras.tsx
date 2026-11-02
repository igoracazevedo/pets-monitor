import { supabase, urlsDasFotos, type Camera } from '../lib/supabase'
import { useDados } from '../lib/dados'
import { haQuanto, minutosDesde } from '../lib/util'

export default function Cameras() {
  const { dados, erro, carregando } = useDados<{ cams: Camera[]; fotos: Record<string, string> }>(
    async () => {
      const { data, error } = await supabase.from('pm_cameras').select('*').order('ordem').order('nome')
      if (error) throw new Error(error.message)
      const cams = (data ?? []) as Camera[]
      return { cams, fotos: await urlsDasFotos(cams.map((c) => c.ultimo_quadro_path)) }
    },
    { cams: [], fotos: {} },
  )
  if (carregando) return <p className="p-6 text-center text-slate-500">Carregando…</p>
  if (erro) return <p className="p-6 text-center text-rose-600">{erro}</p>
  if (dados.cams.length === 0) return <p className="vidro p-6 text-center text-slate-500">As câmeras aparecem aqui assim que o programa de casa rodar a primeira varredura.</p>
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {dados.cams.map((c) => {
        const fora = c.ultimo_status === 'erro' || minutosDesde(c.ultima_leitura) > 5
        return (
          <article key={c.id} className={`vidro overflow-hidden ${c.ativo ? '' : 'opacity-60'}`}>
            {c.ultimo_quadro_path && dados.fotos[c.ultimo_quadro_path] ? (
              <img src={dados.fotos[c.ultimo_quadro_path]} alt={c.nome} className="aspect-video w-full object-cover" loading="lazy" />
            ) : (
              <div className="flex aspect-video items-center justify-center bg-slate-100 text-slate-400">sem imagem</div>
            )}
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
  )
}
