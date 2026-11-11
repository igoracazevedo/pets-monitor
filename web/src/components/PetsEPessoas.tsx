import { useState } from 'react'
import Pets from './Pets'
import Pessoas from './Pessoas'
import Catalogo from './Catalogo'

/** Pets e pessoas na mesma aba, com um seletor no topo. */
export default function PetsEPessoas({ admin }: { admin: boolean }) {
  const [parte, setParte] = useState<'pets' | 'pessoas' | 'objetos'>('pets')
  return (
    <div className="space-y-4">
      <div className="mx-auto flex w-fit gap-1 rounded-full bg-slate-100 p-1">
        {(['pets', 'pessoas', 'objetos'] as const).map((p) => (
          <button
            key={p}
            onClick={() => setParte(p)}
            className={`rounded-full px-4 py-1.5 text-[13px] font-semibold transition ${parte === p ? 'bg-white/90 text-black' : 'text-slate-500'}`}
          >
            {p === 'pets' ? 'Pets' : p === 'pessoas' ? 'Pessoas' : 'Objetos'}
          </button>
        ))}
      </div>
      {parte === 'pets' ? <Pets admin={admin} /> : parte === 'pessoas' ? <Pessoas admin={admin} /> : <Catalogo admin={admin} />}
    </div>
  )
}
