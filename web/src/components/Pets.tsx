import { useRef, useState } from 'react'
import { Camera, Dog, ImagePlus, Plus, Trash2, X } from 'lucide-react'
import { recortarQuadrado, reduzirImagem, supabase, urlsDosPets, type Pet, type PetFoto } from '../lib/supabase'
import { useDados } from '../lib/dados'

type Dados = { pets: Pet[]; fotos: PetFoto[]; urls: Record<string, string> }

async function carregar(): Promise<Dados> {
  const [p, f] = await Promise.all([supabase.from('pm_pets').select('*').order('nome'), supabase.from('pm_pet_fotos').select('*').order('created_at')])
  if (p.error) throw new Error(p.error.message)
  const fotos = (f.data ?? []) as PetFoto[]
  const urls: Record<string, string> = {}
  const todos = [...fotos.map((x) => x.path), ...((p.data ?? []) as Pet[]).map((x) => x.foto_perfil_path ?? '')]
  Object.assign(urls, await urlsDosPets(todos))
  return { pets: (p.data ?? []) as Pet[], fotos, urls }
}

export default function Pets({ admin }: { admin: boolean }) {
  const { dados, erro, carregando, recarregar } = useDados<Dados>(carregar, { pets: [], fotos: [], urls: {} }, 60000)
  const [nome, setNome] = useState('')
  const [especie, setEspecie] = useState('cachorro')
  const [porte, setPorte] = useState('')
  const [msg, setMsg] = useState('')
  const [enviando, setEnviando] = useState<string | null>(null)
  const alvo = useRef<string | null>(null)
  const input = useRef<HTMLInputElement>(null)
  const inputPerfil = useRef<HTMLInputElement>(null)
  const alvoPerfil = useRef<Pet | null>(null)

  const falha = (e: unknown) => setMsg(e instanceof Error ? e.message : (e as { message?: string })?.message ?? String(e))

  async function criar(e: React.FormEvent) {
    e.preventDefault()
    if (!nome.trim()) return
    const { error } = await supabase.from('pm_pets').insert({ nome: nome.trim(), especie, porte: porte || null })
    if (error) return falha(error)
    setNome('')
    setPorte('')
    setMsg('')
    await recarregar()
  }

  async function enviar(petId: string, arquivos: FileList) {
    setEnviando(petId)
    setMsg('')
    try {
      for (const arq of Array.from(arquivos)) {
        const jpeg = await reduzirImagem(arq)
        const path = `${petId}/${crypto.randomUUID()}.jpg`
        const up = await supabase.storage.from('pm-fotos-pets').upload(path, jpeg, { contentType: 'image/jpeg' })
        if (up.error) throw up.error
        const ins = await supabase.from('pm_pet_fotos').insert({ pet_id: petId, path })
        if (ins.error) throw ins.error
      }
      await supabase.from('pm_pets').update({ precisa_reaprender: true }).eq('id', petId)
    } catch (e) {
      falha(e)
    } finally {
      setEnviando(null)
      await recarregar()
    }
  }

  async function trocarPerfil(p: Pet, arq: File) {
    setEnviando(p.id)
    setMsg('')
    try {
      const path = `${p.id}/perfil-${crypto.randomUUID()}.jpg`
      const up = await supabase.storage.from('pm-fotos-pets').upload(path, await recortarQuadrado(arq), { contentType: 'image/jpeg' })
      if (up.error) throw up.error
      const { error } = await supabase.from('pm_pets').update({ foto_perfil_path: path }).eq('id', p.id)
      if (error) throw error
      if (p.foto_perfil_path) await supabase.storage.from('pm-fotos-pets').remove([p.foto_perfil_path])
    } catch (e) {
      falha(e)
    } finally {
      setEnviando(null)
      await recarregar()
    }
  }

  async function apagarFoto(f: PetFoto) {
    await supabase.storage.from('pm-fotos-pets').remove([f.path])
    const { error } = await supabase.from('pm_pet_fotos').delete().eq('id', f.id)
    if (error) return falha(error)
    await supabase.from('pm_pets').update({ precisa_reaprender: true }).eq('id', f.pet_id)
    await recarregar()
  }

  async function apagarPet(p: Pet) {
    if (!confirm(`Remover ${p.nome} e todas as fotos dele?`)) return
    const paths = [...dados.fotos.filter((f) => f.pet_id === p.id).map((f) => f.path), ...(p.foto_perfil_path ? [p.foto_perfil_path] : [])]
    if (paths.length) await supabase.storage.from('pm-fotos-pets').remove(paths)
    const { error } = await supabase.from('pm_pets').delete().eq('id', p.id)
    if (error) falha(error)
    await recarregar()
  }

  async function salvarPorte(p: Pet, v: string) {
    const { error } = await supabase.from('pm_pets').update({ porte: v || null, precisa_reaprender: true }).eq('id', p.id)
    if (error) falha(error)
    await recarregar()
  }

  if (carregando) return <p className="p-6 text-center text-slate-500">Carregando…</p>
  if (erro) return <p className="p-6 text-center text-rose-600">{erro}</p>

  return (
    <div className="space-y-4">
      {msg && <p className="text-sm text-rose-600">{msg}</p>}
      <input ref={inputPerfil} type="file" accept="image/*" hidden onChange={(e) => { const a = e.target.files?.[0]; const p = alvoPerfil.current; e.target.value = ''; if (a && p) void trocarPerfil(p, a) }} />
      <input ref={input} type="file" accept="image/*" multiple hidden onChange={(e) => e.target.files?.length && alvo.current && void enviar(alvo.current, e.target.files).then(() => input.current && (input.current.value = ''))} />

      {dados.pets.map((p) => {
        const fotos = dados.fotos.filter((f) => f.pet_id === p.id)
        return (
          <section key={p.id} className="vidro space-y-3 p-4">
            <div className="flex items-start gap-3">
              <button
                type="button"
                disabled={!admin || enviando === p.id}
                aria-label={`Trocar foto de perfil de ${p.nome}`}
                className="relative h-16 w-16 shrink-0 overflow-hidden rounded-2xl bg-cyan-700/10 text-cyan-800"
                onClick={() => { alvoPerfil.current = p; inputPerfil.current?.click() }}
              >
                {p.foto_perfil_path && dados.urls[p.foto_perfil_path] ? (
                  <img src={dados.urls[p.foto_perfil_path]} alt={p.nome} className="h-full w-full object-cover" />
                ) : (
                  <Dog size={28} className="mx-auto" />
                )}
                {admin && (
                  <span className="absolute inset-x-0 bottom-0 flex justify-center bg-black/45 py-0.5 text-white">
                    <ImagePlus size={12} />
                  </span>
                )}
              </button>
              <div className="min-w-0 flex-1">
                <h2 className="text-lg font-extrabold text-slate-900">{p.nome}</h2>
                <p className="text-[12px] text-slate-500">
                  {p.especie === 'gato' ? 'Gato' : 'Cachorro'} · {fotos.length} foto(s)
                  {p.precisa_reaprender ? ' · aguardando o programa de casa aprender' : p.perfil ? ' · reconhecimento pronto' : ' · sem fotos ensinadas'}
                </p>
              </div>
              {admin && (
                <button aria-label={`Remover ${p.nome}`} className="text-rose-600" onClick={() => void apagarPet(p)}>
                  <Trash2 size={16} />
                </button>
              )}
            </div>

            {admin && (
              <label className="flex items-center gap-2 text-[12px] text-slate-600">
                Porte
                <select value={p.porte ?? ''} onChange={(e) => void salvarPorte(p, e.target.value)}>
                  <option value="">não informado</option>
                  <option value="pequeno">menor da casa</option>
                  <option value="medio">médio</option>
                  <option value="grande">maior da casa</option>
                </select>
              </label>
            )}

            <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
              {fotos.map((f) => (
                <div key={f.id} className="relative aspect-square overflow-hidden rounded-xl bg-slate-100">
                  {dados.urls[f.path] && <img src={dados.urls[f.path]} alt="" className="h-full w-full object-cover" loading="lazy" />}
                  {admin && (
                    <button aria-label="Apagar foto" className="absolute right-1 top-1 rounded-full bg-black/55 p-1 text-white" onClick={() => void apagarFoto(f)}>
                      <X size={12} />
                    </button>
                  )}
                </div>
              ))}
              {admin && (
                <button
                  className="flex aspect-square flex-col items-center justify-center gap-1 rounded-xl border-2 border-dashed border-cyan-700/40 text-[11px] font-semibold text-cyan-800 disabled:opacity-50"
                  disabled={enviando === p.id}
                  onClick={() => {
                    alvo.current = p.id
                    input.current?.click()
                  }}
                >
                  <Camera size={20} />
                  {enviando === p.id ? 'Enviando…' : 'Adicionar fotos'}
                </button>
              )}
            </div>
            <p className="text-[11px] text-slate-500">Melhor com o pet sozinho na foto, de dia e à noite. Prints das câmeras funcionam muito bem.</p>
          </section>
        )
      })}

      {dados.pets.length === 0 && <p className="vidro p-6 text-center text-slate-500">Nenhum pet ainda.</p>}

      {admin ? (
        <form onSubmit={criar} className="vidro space-y-3 p-4">
          <h2 className="font-bold text-slate-900">Novo pet</h2>
          <input value={nome} onChange={(e) => setNome(e.target.value)} placeholder="Nome" className="w-full" />
          <div className="flex gap-2">
            <select value={especie} onChange={(e) => setEspecie(e.target.value)} className="flex-1">
              <option value="cachorro">Cachorro</option>
              <option value="gato">Gato</option>
            </select>
            <select value={porte} onChange={(e) => setPorte(e.target.value)} className="flex-1">
              <option value="">Porte</option>
              <option value="pequeno">menor da casa</option>
              <option value="medio">médio</option>
              <option value="grande">maior da casa</option>
            </select>
            <button className="pilula" aria-label="Adicionar pet">
              <Plus size={16} />
            </button>
          </div>
          <p className="text-[11px] text-slate-500">Depois de criar, adicione as fotos no cartão dele.</p>
        </form>
      ) : (
        <p className="text-center text-[12px] text-slate-500">Só administradores cadastram pets e fotos.</p>
      )}
    </div>
  )
}
