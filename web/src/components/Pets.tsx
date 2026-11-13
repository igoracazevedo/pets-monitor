import { useRef, useState } from 'react'
import { SeletorCor } from './SeletorCor'
import { corPadraoPet, corValida } from '../lib/cores'
import { Dog, ImagePlus, Plus, Trash2 } from 'lucide-react'
import { recortarQuadrado, reduzirImagem, supabase, urlsDasFotos, urlsDosPets, type Pet, type PetFoto } from '../lib/supabase'
import { Galeria } from './Galeria'
import { useDados } from '../lib/dados'

type Achada = { id: number; pet_id: string; visto_em: string; snapshot_path: string | null; camera_id: string }
type Dados = { pets: Pet[]; fotos: PetFoto[]; urls: Record<string, string>; achadas: Achada[]; achadasUrls: Record<string, string>; cams: Record<string, string> }

async function carregar(): Promise<Dados> {
  const [p, f, c] = await Promise.all([
    supabase.from('pm_pets').select('*').order('nome'),
    supabase.from('pm_pet_fotos').select('*').order('created_at'),
    supabase.from('pm_cameras').select('id,nome'),
  ])
  if (p.error) throw new Error(p.error.message)
  const fotos = (f.data ?? []) as PetFoto[]
  const urls: Record<string, string> = {}
  const todos = [...fotos.map((x) => x.path), ...((p.data ?? []) as Pet[]).map((x) => x.foto_perfil_path ?? '')]
  Object.assign(urls, await urlsDosPets(todos))
  // uma consulta por pet: um pet muito visto (ex.: Mavi) não pode esconder os avistamentos dos outros
  const porPet = await Promise.all(
    ((p.data ?? []) as Pet[]).map((pet) =>
      supabase.from('pm_avistamentos').select('id,pet_id,visto_em,snapshot_path,camera_id').eq('pet_id', pet.id).not('snapshot_path', 'is', null).order('visto_em', { ascending: false }).limit(80),
    ),
  )
  const poucas = porPet.flatMap((r) => ((r.data ?? []) as Achada[]).filter((x, i, l) => l.findIndex((y) => y.snapshot_path === x.snapshot_path) === i).slice(0, 24))
  return { pets: (p.data ?? []) as Pet[], fotos, urls, achadas: poucas, achadasUrls: await urlsDasFotos(poucas.map((x) => x.snapshot_path)), cams: Object.fromEntries(((c.data ?? []) as { id: string; nome: string }[]).map((x) => [x.id, x.nome])) }
}

export default function Pets({ admin }: { admin: boolean }) {
  const { dados, erro, carregando, recarregar } = useDados<Dados>(carregar, { pets: [], fotos: [], urls: {}, achadas: [], achadasUrls: {}, cams: {} }, 60000)
  const [nome, setNome] = useState('')
  const [especie, setEspecie] = useState('cachorro')
  const [porte, setPorte] = useState('')
  const [msg, setMsg] = useState('')
  const [enviando, setEnviando] = useState<string | null>(null)
  const alvo = useRef<string | null>(null)
  const input = useRef<HTMLInputElement>(null)
  const inputCamera = useRef<HTMLInputElement>(null)
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

  async function enviar(petId: string, arquivos: File[]) {
    setEnviando(petId)
    setMsg('')
    try {
      for (const arq of arquivos) {
        const jpeg = await reduzirImagem(arq)
        const path = `${petId}/${crypto.randomUUID()}.jpg`
        const up = await supabase.storage.from('pm-fotos-pets').upload(path, jpeg, { contentType: 'image/jpeg', cacheControl: '31536000' })
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
      const up = await supabase.storage.from('pm-fotos-pets').upload(path, await recortarQuadrado(arq), { contentType: 'image/jpeg', cacheControl: '31536000' })
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

  async function mudarCor(p: Pet, cor: string) {
    const { error } = await supabase.from('pm_pets').update({ cor }).eq('id', p.id)
    if (error) falha(error)
    await recarregar()
  }

  async function alternarAviso(p: Pet, v: boolean) {
    const { error } = await supabase.from('pm_pets').update({ notificar: v }).eq('id', p.id)
    if (error) falha(error)
    await recarregar()
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
      <input ref={inputPerfil} type="file" accept="image/*,.heic,.heif" hidden onChange={(e) => { const a = e.target.files?.[0]; const p = alvoPerfil.current; e.target.value = ''; if (a && p) void trocarPerfil(p, a) }} />
      <input ref={inputCamera} type="file" accept="image/*" capture="environment" hidden onChange={(e) => { const f = Array.from(e.target.files ?? []); const id = alvo.current; e.target.value = ''; if (f.length && id) void enviar(id, f) }} />
      <input ref={input} type="file" accept="image/*,.heic,.heif" multiple hidden onChange={(e) => { const f = Array.from(e.target.files ?? []); e.target.value = ''; if (f.length && alvo.current) void enviar(alvo.current, f) }} />

      {dados.pets.map((p, idx) => {
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

            {admin && <SeletorCor valor={corValida(p.cor) ? p.cor : corPadraoPet(idx)} onMudar={(c) => void mudarCor(p, c)} />}
            {admin && (
              <label className="flex items-center gap-2 text-[12px] text-slate-600">
                <input type="checkbox" checked={p.notificar} onChange={(e) => void alternarAviso(p, e.target.checked)} />
                Avisar no celular quando encontrar
              </label>
            )}
            <Galeria
              enviadas={fotos.map((f) => ({ id: f.id, url: dados.urls[f.path] }))}
              encontradas={dados.achadas.filter((x) => x.pet_id === p.id).map((x) => ({ id: String(x.id), url: x.snapshot_path ? dados.achadasUrls[x.snapshot_path] : undefined, legenda: `${dados.cams[x.camera_id] ?? 'Câmera'} · ${new Date(x.visto_em).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}` }))}
              admin={admin}
              enviando={enviando === p.id}
              onApagar={(id) => { const f = fotos.find((x) => x.id === id); if (f) void apagarFoto(f) }}
              onAdicionar={(modo) => { alvo.current = p.id; (modo === 'camera' ? inputCamera : input).current?.click() }}
              dica="Melhor com o pet sozinho na foto, de dia e à noite. Prints das câmeras funcionam muito bem."
            />
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
