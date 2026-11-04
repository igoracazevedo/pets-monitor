import { useState } from 'react'
import Pets from './Pets'
import Pessoas from './Pessoas'

/** Pets e pessoas na mesma aba, com um seletor no topo. */
export default function PetsEPessoas({ admin }: { admin: boolean }) {
  const [parte, setParte] = useState<'pets' | 'pessoas'>('pets')
  return (
    <div className="space-y-4">
      <div className="mx-auto flex w-fit gap-1 rounded-full bg-slate-100 p-1">
        {(['pets', 'pessoas'] as const).map((p) => (
          <button
            key={p}
            onClick={() => setParte(p)}
            className={`rounded-full px-5 py-1.5 text-[13px] font-semibold transition ${parte === p ? 'bg-white text-[#0e7490] shadow-sm' : 'text-slate-500'}`}
          >
            {p === 'pets' ? 'Pets' : 'Pessoas'}
          </button>
        ))}
      </div>
      {parte === 'pets' ? <Pets admin={admin} /> : <Pessoas admin={admin} />}
    </div>
  )
}
