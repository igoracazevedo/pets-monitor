import { supabase, urlsDasFotos, type Camera, type ObjetoCatalogo, type Pet, type Zona } from '../lib/supabase'
import { useDados } from '../lib/dados'
import { haQuanto } from '../lib/util'
import { useVisualizador } from './Visualizador'

type Dados = { objetos: ObjetoCatalogo[]; zonas: Zona[]; pets: Pet[]; cams: Record<string, string>; fotos: Record<string, string>; semTabela: boolean }
const NOME: Record<string, string> = { bebedouro: 'Bebedouro', comedouro: 'Comedouro', banheiro: 'Banheiro', cama: 'Cama' }

async function carregar(): Promise<Dados> {
  const [o, z, p, c] = await Promise.all([
    supabase.from('pm_objetos').select('zona_id,pet_id,tipo,camera_id,imagem_path,sumido,visto_em'),
    supabase.from('pm_zonas').select('*'),
    supabase.from('pm_pets').select('*').order('nome'),
    supabase.from('pm_cameras').select('id,nome'),
  ])
  const objetos = (o.data ?? []) as ObjetoCatalogo[]
  return {
    objetos,
    zonas: (z.data ?? []) as Zona[],
    pets: (p.data ?? []) as Pet[],
    cams: Object.fromEntries(((c.data ?? []) as Pick<Camera, 'id' | 'nome'>[]).map((x) => [x.id, x.nome])),
    fotos: await urlsDasFotos(objetos.map((x) => x.imagem_path)),
    semTabela: !!o.error,
  }
}

/** Catálogo: cada objeto marcado de cada pet, com a aparência aprendida e onde está agora (acompanha mudança de lugar e de câmera). */
export default function Catalogo() {
  const { dados, carregando } = useDados<Dados>(carregar, { objetos: [], zonas: [], pets: [], cams: {}, fotos: {}, semTabela: false }, 30000)
  const { abrir, janela } = useVisualizador()
  if (carregando) return <p className="py-8 text-center text-slate-400">Carregando…</p>
  if (dados.semTabela) return <p className="vidro p-4 text-sm text-slate-600">A tabela do catálogo ainda não existe: rode o trecho SQL do catálogo no Supabase.</p>
  const grupos = [...dados.pets.map((p) => ({ id: p.id as string | null, nome: p.nome })), { id: null as string | null, nome: 'Sem dono' }]
  const zonaDe = (id: string) => dados.zonas.find((z) => z.id === id)
  return (
    <div className="space-y-4">
      {dados.objetos.length === 0 && (
        <p className="vidro p-5 text-center text-sm text-slate-500">Nenhum objeto ainda. Marque o bebedouro, comedouro, banheiro ou cama de cada pet nas fotos (Histórico ou Câmeras) e o programa de casa aprende a aparência de cada um em alguns minutos.</p>
      )}
      {grupos.map((g) => {
        const lista = dados.objetos.filter((o) => o.pet_id === g.id)
        if (lista.length === 0) return null
        return (
          <section key={g.id ?? 'sem'} className="vidro space-y-3 p-4">
            <h2 className="font-bold text-slate-900">{g.nome}</h2>
            <ul className="space-y-3">
              {lista.map((o) => {
                const origem = zonaDe(o.zona_id)?.camera_id
                const mudou = !!o.camera_id && !!origem && o.camera_id !== origem
                const foto = o.imagem_path ? dados.fotos[o.imagem_path] : undefined
                return (
                  <li key={o.zona_id} className="flex items-center gap-3">
                    {foto ? (
                      <button onClick={() => abrir([{ id: o.zona_id, url: foto, titulo: `${NOME[o.tipo]} · ${g.nome}`, legenda: '' }])} className="shrink-0">
                        <img src={foto} alt="" className="h-14 w-14 rounded-xl bg-slate-100 object-cover" />
                      </button>
                    ) : (
                      <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-xl bg-slate-100 text-[10px] text-slate-400">aprendendo</span>
                    )}
                    <div className="min-w-0 flex-1">
                      <p className="font-semibold text-slate-900">{NOME[o.tipo] ?? o.tipo}</p>
                      <p className="text-[13px] text-slate-600">
                        {o.sumido ? 'Não estou vendo agora' : `Agora em ${o.camera_id ? dados.cams[o.camera_id] ?? 'câmera' : '—'}`}
                        {mudou && !o.sumido && <span className="ml-2 rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-800">mudou de câmera</span>}
                      </p>
                      {o.visto_em && <p className="text-[11px] text-slate-400">conferido {haQuanto(o.visto_em)}</p>}
                    </div>
                  </li>
                )
              })}
            </ul>
          </section>
        )
      })}
      <p className="text-center text-[11px] text-slate-400">Se a miniatura estiver errada, apague o local na foto e marque de novo: ele aprende outra vez.</p>
      {janela}
    </div>
  )
}
