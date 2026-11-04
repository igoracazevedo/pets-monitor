import { useState } from 'react'
import { Trash2 } from 'lucide-react'
import { supabase, urlsDasFotos, type Camera, type ObjetoCatalogo, type Pet } from '../lib/supabase'
import { useDados } from '../lib/dados'
import { haQuanto } from '../lib/util'
import { useVisualizador } from './Visualizador'

type Dados = { objetos: ObjetoCatalogo[]; pets: Pet[]; cams: Record<string, string>; fotos: Record<string, string>; semTabela: boolean }
const NOME: Record<string, string> = { bebedouro: 'Bebedouro', comedouro: 'Comedouro', banheiro: 'Banheiro', cama: 'Cama' }

async function carregar(): Promise<Dados> {
  const [o, p, c] = await Promise.all([
    supabase.from('pm_objetos').select('*').order('created_at'),
    supabase.from('pm_pets').select('*').order('nome'),
    supabase.from('pm_cameras').select('id,nome'),
  ])
  const objetos = (o.data ?? []) as ObjetoCatalogo[]
  return {
    objetos,
    pets: (p.data ?? []) as Pet[],
    cams: Object.fromEntries(((c.data ?? []) as Pick<Camera, 'id' | 'nome'>[]).map((x) => [x.id, x.nome])),
    fotos: await urlsDasFotos(objetos.map((x) => x.imagem_path)),
    semTabela: !!o.error,
  }
}

/** Catálogo: os objetos de cada pet (criados ao marcar um local numa foto). Ficam aqui, e o programa de casa os procura onde estiverem, até você apagar. */
export default function Catalogo({ admin }: { admin: boolean }) {
  const { dados, carregando, recarregar } = useDados<Dados>(carregar, { objetos: [], pets: [], cams: {}, fotos: {}, semTabela: false }, 30000)
  const { abrir, janela } = useVisualizador()
  const [erro, setErro] = useState('') // hooks sempre antes de qualquer return antecipado

  async function definirDono(o: ObjetoCatalogo, petId: string) {
    setErro('')
    const a = await supabase.from('pm_objetos').update({ pet_id: petId || null }).eq('id', o.id)
    if (a.error) return setErro(a.error.message)
    if (o.zona_id) await supabase.from('pm_zonas').update({ pet_id: petId || null }).eq('id', o.zona_id) // a marcação na foto muda de cor/nome junto
    void recarregar()
  }
  async function apagar(o: ObjetoCatalogo) {
    if (!window.confirm(`Apagar este ${NOME[o.tipo]?.toLowerCase() ?? 'objeto'} do catálogo? Ele deixa de ser procurado e a marcação nas fotos também some.`)) return
    setErro('')
    const a = await supabase.from('pm_objetos').delete().eq('id', o.id)
    if (a.error) return setErro(a.error.message)
    if (o.zona_id) await supabase.from('pm_zonas').delete().eq('id', o.zona_id)
    if (o.imagem_path) await supabase.storage.from('pm-snapshots').remove([o.imagem_path])
    void recarregar()
  }

  if (carregando) return <p className="py-8 text-center text-slate-400">Carregando…</p>
  if (dados.semTabela) return <p className="vidro p-4 text-sm text-slate-600">A tabela do catálogo ainda não existe: rode o SQL do catálogo no Supabase.</p>
  const grupos = [...dados.pets.map((p) => ({ id: p.id as string | null, nome: p.nome })), { id: null as string | null, nome: 'Sem dono' }]
  return (
    <div className="space-y-4">
      {dados.objetos.length === 0 && (
        <p className="vidro p-5 text-center text-sm text-slate-500">Nenhum objeto ainda. Marque o bebedouro, comedouro, banheiro ou cama de cada pet numa foto (Histórico ou Câmeras): o objeto entra aqui com o recorte da foto e fica até você apagar.</p>
      )}
      {grupos.map((g) => {
        const lista = dados.objetos.filter((o) => o.pet_id === g.id)
        if (lista.length === 0) return null
        return (
          <section key={g.id ?? 'sem'} className="vidro space-y-3 p-4">
            <h2 className="font-bold text-slate-900">{g.nome}</h2>
            <ul className="space-y-3">
              {lista.map((o) => {
                const mudou = !!o.camera_id && !!o.camera_origem && o.camera_id !== o.camera_origem
                const foto = o.imagem_path ? dados.fotos[o.imagem_path] : undefined
                return (
                  <li key={o.id} className="flex items-center gap-3">
                    {foto ? (
                      <button onClick={() => abrir([{ id: o.id, url: foto, titulo: `${NOME[o.tipo]} · ${g.nome}`, legenda: '' }])} className="shrink-0">
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
                        {!o.zona_id && <span className="ml-2 rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-500">sem marcação na foto</span>}
                      </p>
                      {o.visto_em && <p className="text-[11px] text-slate-400">conferido {haQuanto(o.visto_em)}</p>}
                      {admin && g.id === null && (
                        <select className="mt-1 w-full max-w-[220px] text-[13px]" value="" onChange={(e) => void definirDono(o, e.target.value)} aria-label="De quem é?">
                          <option value="">De quem é?</option>
                          {dados.pets.map((p) => (
                            <option key={p.id} value={p.id}>{p.nome}</option>
                          ))}
                        </select>
                      )}
                    </div>
                    {admin && (
                      <button onClick={() => void apagar(o)} className="shrink-0 rounded-full p-2 text-rose-600 hover:bg-rose-50" aria-label="Apagar objeto" title="Apagar">
                        <Trash2 size={18} strokeWidth={1.9} />
                      </button>
                    )}
                  </li>
                )
              })}
            </ul>
          </section>
        )
      })}
      {erro && <p className="text-sm text-rose-600">{erro}</p>}
      <p className="text-center text-[11px] text-slate-400">Tirar a marcação da foto não apaga o objeto: ele continua aqui e continua sendo procurado. Para remover de vez, use a lixeira.</p>
      {janela}
    </div>
  )
}
