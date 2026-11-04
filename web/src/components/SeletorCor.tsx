import { PALETA } from '../lib/cores'

/** Bolinhas da paleta + qualquer cor pelo seletor do aparelho. */
export function SeletorCor({ valor, onMudar }: { valor: string; onMudar: (cor: string) => void }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-[12px] text-slate-600">
      <span className="mr-1">Cor da marcação</span>
      {PALETA.map((c) => (
        <button key={c} type="button" aria-label={`Cor ${c}`} onClick={() => onMudar(c)} className="h-6 w-6 rounded-full border-2" style={{ background: c, borderColor: valor.toLowerCase() === c ? '#0b0b0b' : 'transparent' }} />
      ))}
      <input type="color" value={valor} onChange={(e) => onMudar(e.target.value)} aria-label="Outra cor" className="h-6 w-8 cursor-pointer !rounded-md !p-0" />
    </div>
  )
}
