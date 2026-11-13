import { useRef, useState } from 'react'
import { SeletorCor } from './SeletorCor'
import { corPadraoPessoa, corValida } from '../lib/cores'
import { Plus, ShieldAlert, Trash2 } from 'lucide-react'
import { reduzirImagem, supabase, urlsDasFotos, urlsDosPets, type Pessoa } from '../lib/supabase'
import { Galeria } from './Galeria'
import { useDados } from '../lib/dados'

type Foto = { id: string; pessoa_id: string; path: string }
type Achada = { id: number; pessoa_id: string; visto_em: string; snapshot_path: string | null; camera_id: string }
type Dados = { pessoas: Pessoa[]; fotos: Foto[]; urls: Record<string, string>; achadas: Achada[]; achadasUrls: Record<string, string>; cams: Record<string, string> }

async function carregar(): Promise<Dados> {
  const [p, f, a, c] = await Promise.all([
    supabase.from('pm_pessoas').select('*').order('nome'),
    supabase.from('pm_pessoa_fotos').select('*').order('created_at'),
    supabase.from('pm_avistamentos').select('id,pessoa_id,visto_em,snapshot_path,camera_id').not('pessoa_id', 'is', null).not('snapshot_path', 'is', null).order('visto_em', { ascending: false }).limit(400),
    supabase.from('pm_cameras').select('id,nome'),
  ])
  if (p.error) throw new Error(p.error.message)
  const fotos = (f.data ?? []) as Foto[]
  const porPessoa = new Map<string, number>()
  const achadas = ((a.data ?? []) as Achada[]).filter((x) => {
    const n = (porPessoa.get(x.pessoa_id) ?? 0) + 1
    porPessoa.set(x.pessoa_id, n)
    return n <= 24
  })
  return { pessoas: (p.data ?? []) as Pessoa[], fotos, urls: await urlsDosPets(fotos.map((x) => x.path)), achadas, achadasUrls: await urlsDasFotos(achadas.map((x) => x.snapshot_path)), cams: Object.fromEntries(((c.data ?? []) as { id: string; nome: string }[]).map((x) => [x.id, x.nome])) }
}

export default function Pessoas({ admin }: { admin: boolean }) {
  const { dados, erro, carregando, recarregar } = useDados<Dados>(carregar, { pessoas: [], fotos: [], urls: {}, achadas: [], achadasUrls: {}, cams: {} }, 60000)
  const [nome, setNome] = useState('')
  const [msg, setMsg] = useState('')
  const [enviando, setEnviando] = useState<string | null>(null)
  const alvo = useRef<string | null>(null)
  const input = useRef<HTMLInputElement>(null)
  const inputCamera = useRef<HTMLInputElement>(null)
  const falha = (e: unknown) => setMsg(e instanceof Error ? e.message : (e as { message?: string })?.message ?? String(e))

  async function criar(e: React.FormEvent) {
    e.preventDefault()
    if (!nome.trim()) return
    const { error } = await supabase.from('pm_pessoas').insert({ nome: nome.trim() })
    if (error) return falha(error)
    setNome('')
    setMsg('')
    await recarregar()
  }

  async function enviar(id: string, arquivos: File[]) {
    setEnviando(id)
    setMsg('')
    try {
      for (const arq of arquivos) {
        const jpeg = await reduzirImagem(arq, 1600)
        const path = `pessoas/${id}/${crypto.randomUUID()}.jpg`
        const up = await supabase.storage.from('pm-fotos-pets').upload(path, jpeg, { contentType: 'image/jpeg', cacheControl: '31536000' })
        if (up.error) throw up.error
        const ins = await supabase.from('pm_pessoa_fotos').insert({ pessoa_id: id, path })
        if (ins.error) throw ins.error
      }
      await supabase.from('pm_pessoas').update({ precisa_reaprender: true }).eq('id', id)
    } catch (e) {
      falha(e)
    } finally {
      setEnviando(null)
      await recarregar()
    }
  }

  async function mudarCor(p: Pessoa, cor: string) {
    const { error } = await supabase.from('pm_pessoas').update({ cor }).eq('id', p.id)
    if (error) falha(error)
    await recarregar()
  }

  async function alternarAviso(p: Pessoa, v: boolean) {
    const { error } = await supabase.from('pm_pessoas').update({ notificar: v }).eq('id', p.id)
    if (error) falha(error)
    await recarregar()
  }

  async function apagarFoto(f: Foto) {
    await supabase.storage.from('pm-fotos-pets').remove([f.path])
    const { error } = await supabase.from('pm_pessoa_fotos').delete().eq('id', f.id)
    if (error) return falha(error)
    await supabase.from('pm_pessoas').update({ precisa_reaprender: true }).eq('id', f.pessoa_id)
    await recarregar()
  }

  async function apagarPessoa(p: Pessoa) {
    if (!confirm(`Remover ${p.nome}? As fotos e o rosto aprendido dessa pessoa serão apagados.`)) return
    const paths = dados.fotos.filter((f) => f.pessoa_id === p.id).map((f) => f.path)
    if (paths.length) await supabase.storage.from('pm-fotos-pets').remove(paths)
    const { error } = await supabase.from('pm_pessoas').delete().eq('id', p.id)
    if (error) falha(error)
    await recarregar()
  }

  if (carregando) return <p className="p-6 text-center text-slate-500">Carregando…</p>
  if (erro) return <p className="p-6 text-center text-rose-600">{erro}</p>
  if (!admin) return <p className="vidro p-6 text-center text-slate-600">Só administradores cadastram pessoas.</p>

  return (
    <div className="space-y-4">
      <p className="vidro flex gap-2 px-3 py-2 text-[12px] text-slate-600">
        <ShieldAlert size={16} className="mt-0.5 shrink-0 text-amber-600" />
        <span>
          Cadastre só quem concordou em ser reconhecido (família, quem mora aqui). O rosto é lido e guardado apenas no PC de casa; o site guarda só o nome e as fotos que você enviar. Para apagar tudo de uma pessoa, remova-a aqui.
        </span>
      </p>
      {msg && <p className="text-sm text-rose-600">{msg}</p>}
      <input ref={inputCamera} type="file" accept="image/*" capture="user" hidden onChange={(e) => { const f = Array.from(e.target.files ?? []); const id = alvo.current; e.target.value = ''; if (f.length && id) void enviar(id, f) }} />
      <input ref={input} type="file" accept="image/*,.heic,.heif" multiple hidden onChange={(e) => { const f = Array.from(e.target.files ?? []); const id = alvo.current; e.target.value = ''; if (f.length && id) void enviar(id, f) }} />

      {dados.pessoas.map((p, idx) => {
        const fotos = dados.fotos.filter((f) => f.pessoa_id === p.id)
        return (
          <section key={p.id} className="vidro space-y-3 p-4">
            <div className="flex items-start justify-between gap-2">
              <div>
                <h2 className="text-lg font-extrabold text-slate-900">{p.nome}</h2>
                <p className="text-[12px] text-slate-500">
                  {fotos.length} foto(s){p.precisa_reaprender ? ' · aguardando o programa de casa aprender o rosto' : fotos.length ? ' · rosto pronto' : ' · sem fotos'}
                </p>
              </div>
              <button aria-label={`Remover ${p.nome}`} className="text-rose-600" onClick={() => void apagarPessoa(p)}>
                <Trash2 size={16} />
              </button>
            </div>
            <SeletorCor valor={corValida(p.cor) ? p.cor : corPadraoPessoa(idx)} onMudar={(c) => void mudarCor(p, c)} />
            <label className="flex items-center gap-2 text-[12px] text-slate-600">
              <input type="checkbox" checked={p.notificar} onChange={(e) => void alternarAviso(p, e.target.checked)} />
              Avisar no celular quando encontrar
            </label>
            <Galeria
              enviadas={fotos.map((f) => ({ id: f.id, url: dados.urls[f.path] }))}
              encontradas={dados.achadas.filter((x) => x.pessoa_id === p.id).map((x) => ({ id: String(x.id), url: x.snapshot_path ? dados.achadasUrls[x.snapshot_path] : undefined, legenda: `${dados.cams[x.camera_id] ?? 'Câmera'} · ${new Date(x.visto_em).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}` }))}
              admin
              enviando={enviando === p.id}
              onApagar={(id) => { const f = fotos.find((x) => x.id === id); if (f) void apagarFoto(f) }}
              onAdicionar={(modo) => { alvo.current = p.id; (modo === 'camera' ? inputCamera : input).current?.click() }}
              dica="Mande 3 a 6 fotos do rosto de frente, bem iluminadas, sem óculos escuros nem boné. Câmeras no teto só reconhecem quando o rosto aparece de frente e grande o bastante."
            />
          </section>
        )
      })}
      {dados.pessoas.length === 0 && <p className="vidro p-6 text-center text-slate-500">Ninguém cadastrado ainda.</p>}

      <form onSubmit={criar} className="vidro space-y-3 p-4">
        <h2 className="font-bold text-slate-900">Nova pessoa</h2>
        <div className="flex gap-2">
          <input value={nome} onChange={(e) => setNome(e.target.value)} placeholder="Nome" className="min-w-0 flex-1" />
          <button className="pilula" aria-label="Adicionar pessoa">
            <Plus size={16} />
          </button>
        </div>
      </form>
    </div>
  )
}
