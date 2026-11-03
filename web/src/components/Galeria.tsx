import { useState } from 'react'
import { Camera, ChevronDown, ImagePlus, X } from 'lucide-react'

export type Miniatura = { id: string; url?: string; legenda?: string }

/** Fotos do cadastro, recolhidas e pequenas: as que você enviou e as que o programa encontrou nas câmeras. */
export function Galeria({
  enviadas,
  encontradas,
  admin,
  enviando,
  onApagar,
  onAdicionar,
  dica,
}: {
  enviadas: Miniatura[]
  encontradas: Miniatura[]
  admin: boolean
  enviando: boolean
  onApagar: (id: string) => void
  onAdicionar: (modo: 'camera' | 'galeria') => void
  dica: string
}) {
  const [aberta, setAberta] = useState(false)
  return (
    <div className="space-y-2">
      <button type="button" onClick={() => setAberta((a) => !a)} className="flex w-full items-center justify-between rounded-xl bg-white/50 px-3 py-2 text-left text-[12px] font-semibold text-slate-700">
        <span>
          Fotos · {enviadas.length} enviada(s) · {encontradas.length} encontrada(s)
        </span>
        <ChevronDown size={16} className={`transition ${aberta ? 'rotate-180' : ''}`} />
      </button>
      {aberta && (
        <div className="space-y-3">
          <div>
            <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">Enviadas por você</p>
            <div className="flex flex-wrap gap-1.5">
              {enviadas.map((f) => (
                <div key={f.id} className="relative h-14 w-14 overflow-hidden rounded-lg bg-slate-100">
                  {f.url && (
                    <a href={f.url} target="_blank" rel="noreferrer">
                      <img src={f.url} alt="" className="h-full w-full object-cover" loading="lazy" />
                    </a>
                  )}
                  {admin && (
                    <button aria-label="Apagar foto" className="absolute right-0.5 top-0.5 rounded-full bg-black/60 p-0.5 text-white" onClick={() => onApagar(f.id)}>
                      <X size={10} />
                    </button>
                  )}
                </div>
              ))}
              {admin && (
                <>
                  <button
                    className="flex h-14 w-14 flex-col items-center justify-center gap-0.5 rounded-lg border-2 border-dashed border-cyan-700/40 text-[9px] font-semibold leading-tight text-cyan-800 disabled:opacity-50"
                    disabled={enviando}
                    onClick={() => onAdicionar('camera')}
                  >
                    <Camera size={16} />
                    {enviando ? 'Enviando' : 'Tirar foto'}
                  </button>
                  <button
                    className="flex h-14 w-14 flex-col items-center justify-center gap-0.5 rounded-lg border-2 border-dashed border-cyan-700/40 text-[9px] font-semibold leading-tight text-cyan-800 disabled:opacity-50"
                    disabled={enviando}
                    onClick={() => onAdicionar('galeria')}
                  >
                    <ImagePlus size={16} />
                    Galeria
                  </button>
                </>
              )}
            </div>
            <p className="mt-1 text-[11px] text-slate-500">{dica}</p>
          </div>
          <div>
            <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">Encontradas nas câmeras</p>
            {encontradas.length === 0 ? (
              <p className="text-[11px] text-slate-500">Ainda nenhuma.</p>
            ) : (
              <div className="flex flex-wrap gap-1.5">
                {encontradas.map((f) => (
                  <a key={f.id} href={f.url} target="_blank" rel="noreferrer" className="relative block h-14 w-[84px] overflow-hidden rounded-lg bg-slate-100" title={f.legenda}>
                    {f.url && <img src={f.url} alt={f.legenda ?? ''} className="h-full w-full object-cover" loading="lazy" />}
                  </a>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
