import { useEffect, useState } from 'react'

/** Tela de abertura: ícone do app animado enquanto o login e os dados carregam (some com fade quando tudo está pronto) */
export function TelaAbertura({ saindo = false, texto = 'Carregando seus dados' }: { saindo?: boolean; texto?: string }) {
  return (
    <div
      className={`fixed inset-0 z-[200] flex flex-col items-center justify-center gap-6 transition-opacity duration-500 ${saindo ? 'opacity-0 pointer-events-none' : 'opacity-100'}`}
      style={{ background: 'radial-gradient(circle at 50% 38%, #0f3a44 0%, #111416 50%, #050607 100%)' }}
      role="status"
      aria-live="polite"
    >
      <div className="relative grid place-items-center">
        <span className="abertura-anel absolute h-36 w-36 rounded-[2.2rem] border-2" style={{ borderColor: 'rgba(103, 232, 249, 0.45)' }} />
        <span className="abertura-anel abertura-anel-2 absolute h-36 w-36 rounded-[2.2rem] border-2" style={{ borderColor: 'rgba(103, 232, 249, 0.45)' }} />
        <img src="/icon-192.png" alt="Pets Monitor" className="abertura-icone relative h-24 w-24 rounded-[1.6rem] shadow-2xl" />
      </div>
      <div className="text-center">
        <p className="text-lg font-bold tracking-tight text-white">Pets Monitor</p>
        <p className="mt-1 flex items-center justify-center gap-1 text-xs font-medium" style={{ color: 'rgba(165, 243, 252, 0.85)' }}>
          {texto}
          <span className="abertura-pontos inline-flex gap-0.5">
            <i className="h-1 w-1 rounded-full" style={{ background: 'rgba(165, 243, 252, 0.85)' }} />
            <i className="h-1 w-1 rounded-full" style={{ background: 'rgba(165, 243, 252, 0.85)' }} />
            <i className="h-1 w-1 rounded-full" style={{ background: 'rgba(165, 243, 252, 0.85)' }} />
          </span>
        </p>
      </div>
    </div>
  )
}

/** Controla a abertura: fica visível até `pronto`; aí faz o fade e sai. Libera sozinha em 25 s se algo travar. */
export function useAbertura(pronto: boolean) {
  const [saindo, setSaindo] = useState(false)
  const [visivel, setVisivel] = useState(true)
  useEffect(() => {
    const t = setTimeout(() => setSaindo(true), 25000)
    return () => clearTimeout(t)
  }, [])
  useEffect(() => {
    if (!pronto) return
    // deixa a tela pintar com os dados antes de tirar a abertura
    requestAnimationFrame(() => requestAnimationFrame(() => setSaindo(true)))
  }, [pronto])
  useEffect(() => {
    if (!saindo) return
    const t = setTimeout(() => setVisivel(false), 550)
    return () => clearTimeout(t)
  }, [saindo])
  return { visivel, saindo }
}
