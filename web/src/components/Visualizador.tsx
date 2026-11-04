import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { ChevronLeft, ChevronRight, ExternalLink, X } from 'lucide-react'

export type Local = { caixa: Caixa; rotulo: string; cor: string }
export type ItemFoto = { id: string; url: string; titulo?: string; legenda?: string; extra?: unknown; locais?: Local[] }
export type Caixa = { x: number; y: number; w: number; h: number }
export type Opcao = { valor: string; nome: string; grupo?: string }
export type Marcacao = { opcoes: Opcao[]; onMarcar: (item: ItemFoto, caixa: Caixa, valor: string) => Promise<void> }
export type AcaoVisualizador = { rotulo: string; ocupado: boolean; onClick: () => void }

/** Foto em tela cheia (no celular as miniaturas ficam pequenas demais). Setas/arrastar para trocar, pinça para ampliar. */
export function Visualizador({ itens, indice, onIndice, onFechar, acao, marcar }: { itens: ItemFoto[]; indice: number; onIndice: (i: number) => void; onFechar: () => void; acao?: AcaoVisualizador; marcar?: Marcacao }) {
  const [modo, setModo] = useState(false)
  const [arrasto, setArrasto] = useState<{ x0: number; y0: number; x1: number; y1: number } | null>(null)
  const [pendente, setPendente] = useState<Caixa | null>(null)
  const [escolha, setEscolha] = useState('')
  const [salvando, setSalvando] = useState(false)
  const [verLocais, setVerLocais] = useState(true)
  const [destaque, setDestaque] = useState<number | null>(null)
  const [feitas, setFeitas] = useState<{ caixa: Caixa; nome: string; foto: string }[]>([])
  const areaImg = useRef<HTMLDivElement>(null)
  const miolo = useRef<HTMLDivElement>(null)
  const [altura, setAltura] = useState(0)
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

  // a foto ocupa só o espaço que sobra entre o cabeçalho e as barras de baixo (a barra de marcação não pode cobrir a imagem)
  useLayoutEffect(() => {
    const el = miolo.current
    if (!el) return
    const medir = () => setAltura(Math.max(120, el.clientHeight - 8))
    medir()
    const ro = new ResizeObserver(medir)
    ro.observe(el)
    return () => ro.disconnect()
  }, [item == null])

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
        ref={miolo}
        className="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden"
        onTouchStart={(e) => (inicioToque.current = !modo && e.touches.length === 1 ? e.touches[0].clientX : null)}
        onTouchEnd={(e) => {
          if (inicioToque.current == null) return
          const dx = e.changedTouches[0].clientX - inicioToque.current
          inicioToque.current = null
          if (Math.abs(dx) > 60) ir(dx < 0 ? 1 : -1)
        }}
      >
        <div ref={areaImg} className="relative inline-block max-h-full max-w-full" onClick={(e) => e.stopPropagation()}>
          <img src={item.url} alt={item.titulo ?? ''} className="block max-w-full object-contain" style={{ touchAction: modo ? 'none' : 'pinch-zoom', maxHeight: altura || undefined }} draggable={false} />
          {verLocais && (item.locais ?? []).map((l, i) => (
            <div key={`l${i}`} className="pointer-events-none absolute" style={{ left: `${l.caixa.x * 100}%`, top: `${l.caixa.y * 100}%`, width: `${l.caixa.w * 100}%`, height: `${l.caixa.h * 100}%`, border: `${destaque === i ? 4 : 2}px ${destaque === i ? 'solid' : 'dashed'} ${l.cor}`, boxShadow: '0 0 0 1px rgba(0,0,0,.55)' }}>
              <span className={`absolute left-0 flex h-5 min-w-5 items-center justify-center rounded px-1 text-[12px] font-extrabold leading-none text-white ${l.caixa.y > 0.07 ? 'bottom-full mb-0.5' : 'top-0'}`} style={{ background: l.cor, textShadow: '0 1px 2px rgba(0,0,0,.7)' }}>{i + 1}</span>
            </div>
          ))}
          {feitas.filter((f) => f.foto === item.id).map((f, i) => (
            <div key={i} className="pointer-events-none absolute border-2 border-emerald-400" style={{ left: `${f.caixa.x * 100}%`, top: `${f.caixa.y * 100}%`, width: `${f.caixa.w * 100}%`, height: `${f.caixa.h * 100}%` }}>
              <span className="absolute -top-5 left-0 rounded bg-emerald-500 px-1 text-[11px] font-bold">{f.nome}</span>
            </div>
          ))}
          {modo && (
            <div
              className="absolute inset-0 cursor-crosshair"
              style={{ touchAction: 'none' }}
              onPointerDown={(e) => {
                const r = e.currentTarget.getBoundingClientRect()
                const x = (e.clientX - r.left) / r.width
                const y = (e.clientY - r.top) / r.height
                e.currentTarget.setPointerCapture(e.pointerId)
                setPendente(null)
                setArrasto({ x0: x, y0: y, x1: x, y1: y })
              }}
              onPointerMove={(e) => {
                if (!arrasto) return
                const r = e.currentTarget.getBoundingClientRect()
                setArrasto({ ...arrasto, x1: Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)), y1: Math.min(1, Math.max(0, (e.clientY - r.top) / r.height)) })
              }}
              onPointerUp={() => {
                if (!arrasto) return
                const caixa = { x: Math.min(arrasto.x0, arrasto.x1), y: Math.min(arrasto.y0, arrasto.y1), w: Math.abs(arrasto.x1 - arrasto.x0), h: Math.abs(arrasto.y1 - arrasto.y0) }
                setArrasto(null)
                if (caixa.w > 0.03 && caixa.h > 0.03) setPendente(caixa)
              }}
            >
              {(arrasto || pendente) && (() => {
                const c = pendente ?? { x: Math.min(arrasto!.x0, arrasto!.x1), y: Math.min(arrasto!.y0, arrasto!.y1), w: Math.abs(arrasto!.x1 - arrasto!.x0), h: Math.abs(arrasto!.y1 - arrasto!.y0) }
                return <div className="absolute border-2 border-amber-300 bg-amber-300/10" style={{ left: `${c.x * 100}%`, top: `${c.y * 100}%`, width: `${c.w * 100}%`, height: `${c.h * 100}%` }} />
              })()}
            </div>
          )}
        </div>
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

      {verLocais && (item.locais?.length ?? 0) > 0 && (
        <div className="flex gap-2 overflow-x-auto bg-black/60 px-4 py-2" onClick={(e) => e.stopPropagation()}>
          {item.locais!.map((l, i) => (
            <button key={i} type="button" onClick={() => setDestaque(destaque === i ? null : i)} className={`flex shrink-0 items-center gap-2 rounded-full px-3 py-1.5 text-[13px] font-semibold ${destaque === i ? 'bg-white text-black' : 'bg-white/15 text-white'}`}>
              <span className="flex h-5 w-5 items-center justify-center rounded-full text-[12px] font-extrabold text-white" style={{ background: l.cor }}>{i + 1}</span>
              {l.rotulo}
            </button>
          ))}
        </div>
      )}
      {modo && marcar && (
        <div className="space-y-2 bg-black/70 px-4 py-3 text-sm" onClick={(e) => e.stopPropagation()}>
          {pendente ? (
            <div className="flex items-center gap-2">
              <select value={escolha} onChange={(e) => setEscolha(e.target.value)} className="min-w-0 flex-1 rounded-lg bg-white px-2 py-2 text-slate-900">
                <option value="">Quem é? / Qual local?</option>
                {[...new Set(marcar.opcoes.map((o) => o.grupo ?? ''))].map((g) => {
                  const itensG = marcar.opcoes.filter((o) => (o.grupo ?? '') === g)
                  const opts = itensG.map((o) => (
                    <option key={o.valor} value={o.valor}>
                      {o.nome}
                    </option>
                  ))
                  return g ? (
                    <optgroup key={g} label={g}>
                      {opts}
                    </optgroup>
                  ) : (
                    opts
                  )
                })}
              </select>
              <button
                disabled={!escolha || salvando}
                className="rounded-full bg-emerald-500 px-4 py-2 font-bold disabled:opacity-50"
                onClick={async () => {
                  setSalvando(true)
                  try {
                    await marcar.onMarcar(item, pendente, escolha)
                    setFeitas((f) => [...f, { caixa: pendente, nome: marcar.opcoes.find((o) => o.valor === escolha)?.nome ?? '', foto: item.id }])
                    setPendente(null)
                    setEscolha('')
                  } finally {
                    setSalvando(false)
                  }
                }}
              >
                {salvando ? 'Salvando…' : 'Salvar'}
              </button>
              <button className="rounded-full bg-white/15 px-3 py-2" onClick={() => setPendente(null)}>
                Refazer
              </button>
            </div>
          ) : (
            <p className="text-white/80">Arraste o dedo sobre cada animal ou pessoa da foto e diga quem é. Dá para marcar vários na mesma foto.</p>
          )}
        </div>
      )}
      <div className="flex items-center justify-between gap-3 px-4 py-3 text-[12px] text-white/70" onClick={(e) => e.stopPropagation()}>
        <span className="shrink-0 whitespace-nowrap">{itens.length > 1 ? `${indice + 1} de ${itens.length}` : ''}</span>
        {itens.some((x) => x.locais?.length) && (
          <button className={`rounded-full px-3 py-2 text-[13px] font-bold ${verLocais ? 'bg-white/90 text-black' : 'bg-white/15 text-white'}`} onClick={() => setVerLocais((v) => !v)}>
            Locais
          </button>
        )}
        {marcar && (
          <button className={`rounded-full px-3 py-2 text-[13px] font-bold sm:px-4 sm:text-sm ${modo ? 'bg-amber-300 text-black' : 'bg-white/15 text-white'}`} onClick={() => { setModo((m) => !m); setPendente(null); setArrasto(null) }}>
            {modo ? 'Terminar marcação' : 'Marcar quem é'}
          </button>
        )}
        {acao && (
          <button disabled={acao.ocupado} onClick={acao.onClick} className="rounded-full bg-white px-3 py-2 text-[13px] font-bold text-[#0e7490] disabled:opacity-60 sm:px-4 sm:text-sm">
            {acao.ocupado ? 'Batendo foto…' : acao.rotulo}
          </button>
        )}
      </div>
    </div>
  )
}

/** Uso simples: `const { abrir, janela } = useVisualizador()`; renderize `{janela}` e chame `abrir(itens, indice)` ao tocar numa foto. */
export function useVisualizador(marcar?: Marcacao) {
  const [estado, setEstado] = useState<{ itens: ItemFoto[]; indice: number } | null>(null)
  return {
    abrir: (itens: ItemFoto[], indice = 0) => itens.length > 0 && setEstado({ itens, indice }),
    janela: estado ? <Visualizador itens={estado.itens} indice={estado.indice} onIndice={(i) => setEstado({ ...estado, indice: i })} onFechar={() => setEstado(null)} marcar={marcar} /> : null,
  }
}
