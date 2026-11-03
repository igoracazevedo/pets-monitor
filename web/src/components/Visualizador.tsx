import { useEffect, useRef, useState } from 'react'
import { ChevronLeft, ChevronRight, ExternalLink, X } from 'lucide-react'

export type ItemFoto = { id: string; url: string; titulo?: string; legenda?: string }
export type AcaoVisualizador = { rotulo: string; ocupado: boolean; onClick: () => void }

/** Foto em tela cheia (no celular as miniaturas ficam pequenas demais). Setas/arrastar para trocar, pinça para ampliar. */
export function Visualizador({ itens, indice, onIndice, onFechar, acao }: { itens: ItemFoto[]; indice: number; onIndice: (i: number) => void; onFechar: () => void; acao?: AcaoVisualizador }) {
  const item = itens[indice]
  const inicioToque = useRef<number | null>(null)
  const ir = (d: number) => itens.length > 1 && onIndice((indice + d + itens.length) % itens.length)

  useEffect(() => {
    const tecla = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onFechar()
      if (e.key === 'ArrowLeft') ir(-1)
      if (e.key === 'ArrowRight') ir(1)
    }
    document.addEventListener('keydown', tecla)
    const rolagem = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', tecla)
      document.body.style.overflow = rolagem
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [indice, itens.length])

  if (!item) return null
  return (
    <div className="fixed inset-0 z-[80] flex flex-col bg-black/95 text-white" onClick={onFechar} role="dialog" aria-modal="true">
      <div className="flex items-center justify-between gap-3 px-4 py-3" onClick={(e) => e.stopPropagation()}>
        <div className="min-w-0">
          {item.titulo && <p className="truncate font-bold">{item.titulo}</p>}
          {item.legenda && <p className="truncate text-[12px] text-white/70">{item.legenda}</p>}
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <a href={item.url} target="_blank" rel="noreferrer" aria-label="Abrir original" className="rounded-full p-2 hover:bg-white/10">
            <ExternalLink size={20} />
          </a>
          <button aria-label="Fechar" className="rounded-full p-2 hover:bg-white/10" onClick={onFechar}>
            <X size={22} />
          </button>
        </div>
      </div>

      <div
        className="relative flex min-h-0 flex-1 items-center justify-center"
        onTouchStart={(e) => (inicioToque.current = e.touches.length === 1 ? e.touches[0].clientX : null)}
        onTouchEnd={(e) => {
          if (inicioToque.current == null) return
          const dx = e.changedTouches[0].clientX - inicioToque.current
          inicioToque.current = null
          if (Math.abs(dx) > 60) ir(dx < 0 ? 1 : -1)
        }}
      >
        <img src={item.url} alt={item.titulo ?? ''} className="max-h-full max-w-full object-contain" style={{ touchAction: 'pinch-zoom' }} onClick={(e) => e.stopPropagation()} />
        {itens.length > 1 && (
          <>
            <button aria-label="Anterior" className="absolute left-2 top-1/2 -translate-y-1/2 rounded-full bg-black/50 p-2 hover:bg-black/70" onClick={(e) => { e.stopPropagation(); ir(-1) }}>
              <ChevronLeft size={24} />
            </button>
            <button aria-label="Próxima" className="absolute right-2 top-1/2 -translate-y-1/2 rounded-full bg-black/50 p-2 hover:bg-black/70" onClick={(e) => { e.stopPropagation(); ir(1) }}>
              <ChevronRight size={24} />
            </button>
          </>
        )}
      </div>

      <div className="flex items-center justify-between gap-3 px-4 py-3 text-[12px] text-white/70" onClick={(e) => e.stopPropagation()}>
        <span>{itens.length > 1 ? `${indice + 1} de ${itens.length}` : ''}</span>
        {acao && (
          <button disabled={acao.ocupado} onClick={acao.onClick} className="rounded-full bg-white px-4 py-2 text-sm font-bold text-[#0e7490] disabled:opacity-60">
            {acao.ocupado ? 'Batendo foto…' : acao.rotulo}
          </button>
        )}
      </div>
    </div>
  )
}

/** Uso simples: `const { abrir, janela } = useVisualizador()`; renderize `{janela}` e chame `abrir(itens, indice)` ao tocar numa foto. */
export function useVisualizador() {
  const [estado, setEstado] = useState<{ itens: ItemFoto[]; indice: number } | null>(null)
  return {
    abrir: (itens: ItemFoto[], indice = 0) => itens.length > 0 && setEstado({ itens, indice }),
    janela: estado ? <Visualizador itens={estado.itens} indice={estado.indice} onIndice={(i) => setEstado({ ...estado, indice: i })} onFechar={() => setEstado(null)} /> : null,
  }
}
