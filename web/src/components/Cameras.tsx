import { useState } from 'react'
import { Camera as CamIcon, Check, ChevronRight, Pencil } from 'lucide-react'
import { supabase, urlsDasFotos, type Camera, type Pet, type Zona } from '../lib/supabase'
import { marcarLocal } from '../lib/objetos'
import { locaisDaCamera, opcoesDeLocais } from '../lib/zonas'
import { useDados } from '../lib/dados'
import { haQuanto, minutosDesde } from '../lib/util'
import { Visualizador, type Caixa, type ItemFoto } from './Visualizador'

const horaCompleta = (iso: string) => new Date(iso).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' })

export default function Cameras({ admin }: { admin: boolean }) {
  const [editando, setEditando] = useState<string | null>(null)
  const [apelido, setApelido] = useState('')
  const [msg, setMsg] = useState('')
  const [buscando, setBuscando] = useState(false)
  const [batendo, setBatendo] = useState<string | null>(null)
  const [ver, setVer] = useState<number | null>(null)
  const { dados, erro, carregando, recarregar } = useDados<{ cams: Camera[]; fotos: Record<string, string>; pets: Pet[]; gente: { id: string; nome: string }[]; zonas: Zona[] }>(
    async () => {
      const [{ data, error }, pets, gente, zonas] = await Promise.all([supabase.from('pm_cameras').select('*').order('ordem').order('nome'), supabase.from('pm_pets').select('*').eq('ativo', true).order('nome'), supabase.from('pm_pessoas').select('id,nome').order('nome'), supabase.from('pm_zonas').select('*')])
      if (error) throw new Error(error.message)
      const cams = (data ?? []) as Camera[]
      return { cams, fotos: await urlsDasFotos(cams.map((c) => c.ultimo_quadro_path)), pets: (pets.data ?? []) as Pet[], gente: (gente.data ?? []) as { id: string; nome: string }[], zonas: (zonas.data ?? []) as Zona[] }
    },
    { cams: [], fotos: {}, pets: [], gente: [], zonas: [] },
    15000,
  )

  // "Ver ao vivo": pede ao programa de casa uma foto nova de cada câmera e mostra a hora de cada captura
  async function pedirFotos(cameraId?: string) {
    if (cameraId) setBatendo(cameraId)
    else setBuscando(true)
    setMsg('')
    try {
      const { data, error } = await supabase.from('pm_pedidos').insert({ tipo: 'fotos', camera_id: cameraId ?? null }).select('id').single()
      if (error || !data) throw error ?? new Error('não consegui enviar o pedido')
      let atendido = false
      for (let i = 0; i < 20 && !atendido; i++) {
        await new Promise((r) => setTimeout(r, 2000))
        const { data: p } = await supabase.from('pm_pedidos').select('atendido_em').eq('id', data.id).single()
        atendido = !!p?.atendido_em
      }
      if (!atendido) setMsg('O programa de casa não respondeu. Confira se o iniciar.bat está aberto no PC.')
      await recarregar()
    } catch (e) {
      setMsg(e instanceof Error ? e.message : (e as { message?: string })?.message ?? String(e))
    } finally {
      setBuscando(false)
      setBatendo(null)
    }
  }

  /** Marca à mão quem está na foto da câmera (o programa não achou sozinho): guarda uma cópia da foto no Histórico e ensina o programa. */
  async function marcarNaCamera(item: ItemFoto, caixa: Caixa, destino: string) {
    const cam = item.extra as Camera
    if (destino.startsWith('zona:')) { // marca um local (banheiro, bebedouro, comedouro, cama) nesta câmera
      const [, t, quem] = destino.split(':')
      await marcarLocal({ cameraId: cam.id, tipo: t, petId: quem === 'todos' ? null : quem, caixa, urlFoto: item.url })
      setMsg('Local marcado e guardado no catálogo de objetos (Pets › Objetos).')
      await recarregar()
      return
    }
    if (!cam.ultimo_quadro_path) throw new Error('Essa câmera ainda não tem foto.')
    const [tipo, id] = destino.split(':')
    const agora = new Date()
    const dest = `avistamentos/${agora.getFullYear()}/${String(agora.getMonth() + 1).padStart(2, '0')}/${String(agora.getDate()).padStart(2, '0')}/${cam.id.slice(0, 8)}-${agora.toTimeString().slice(0, 8).replace(/:/g, '')}-manual.jpg`
    const cp = await supabase.storage.from('pm-snapshots').copy(cam.ultimo_quadro_path, dest) // a foto da câmera é sobrescrita a cada varredura; a cópia fica
    if (cp.error) throw new Error(`Não consegui guardar a foto (${cp.error.message}). Rode o schema.sql de novo no Supabase.`)
    const pet = tipo === 'pet' ? dados.pets.find((p) => p.id === id) : undefined
    const box = { x: Number(caixa.x.toFixed(4)), y: Number(caixa.y.toFixed(4)), w: Number(caixa.w.toFixed(4)), h: Number(caixa.h.toFixed(4)) }
    const visto = agora.toISOString()
    const ins = await supabase.from('pm_avistamentos').insert({ ...box, camera_id: cam.id, snapshot_path: dest, visto_em: visto, confianca: 1, identificacao: 'manual', especie: tipo === 'pessoa' ? 'pessoa' : (pet?.especie ?? 'cachorro'), pet_id: tipo === 'pet' ? id : null, pessoa_id: tipo === 'pessoa' ? id : null })
    if (ins.error) throw ins.error
    if (tipo === 'pet') {
      const up = await supabase.from('pm_ultima_posicao').upsert({ pet_id: id, camera_id: cam.id, visto_em: visto, confianca: 1, ...box, snapshot_path: dest, foto_em: cam.foto_em ?? visto })
      if (up.error) throw up.error
    }
    await supabase.from('pm_correcoes').insert({ camera_id: cam.id, snapshot_path: dest, ...box, pet_id: tipo === 'pet' ? id : null, pessoa_id: tipo === 'pessoa' ? id : null })
    setMsg(`Pronto: ${tipo === 'pet' ? pet?.nome : dados.gente.find((g) => g.id === id)?.nome} marcado(a) em ${cam.nome}. Aparece no Histórico e na tela Início.`)
  }

  async function salvarApelido(id: string) {
    const nome = apelido.trim()
    if (!nome) return setEditando(null)
    const { error } = await supabase.from('pm_cameras').update({ nome }).eq('id', id)
    setMsg(error ? (error.message.includes('duplicate') ? 'Já existe uma câmera com esse nome.' : error.message) : '')
    if (!error) setEditando(null)
    await recarregar()
  }

  if (carregando) return <p className="p-6 text-center text-slate-500">Carregando…</p>
  if (erro) return <p className="p-6 text-center text-rose-400">{erro}</p>
  const visiveis = dados.cams.filter((c) => c.ativo)
  const ocultas = dados.cams.length - visiveis.length
  const urlDe = (c: Camera) => {
    const base = c.ultimo_quadro_path ? dados.fotos[c.ultimo_quadro_path] : undefined
    return base ? `${base}${base.includes('?') ? '&' : '?'}t=${c.foto_em ? Date.parse(c.foto_em) : 0}` : undefined
  }
  const itens: ItemFoto[] = visiveis.flatMap((c) => {
    const url = urlDe(c)
    return url ? [{ id: c.id, url, extra: c, locais: locaisDaCamera(dados.pets, dados.zonas, c.id), titulo: c.nome, legenda: c.foto_em ? `Foto de ${horaCompleta(c.foto_em)} (${haQuanto(c.foto_em)})` : undefined }] : []
  })
  if (dados.cams.length === 0) return <p className="vidro p-6 text-center text-slate-500">As câmeras aparecem aqui assim que o programa de casa rodar a primeira varredura.</p>
  const estaFora = (c: Camera) => c.ultimo_status === 'erro' || minutosDesde(c.ultima_leitura) > 5
  const online = visiveis.filter((c) => !estaFora(c))
  const offline = visiveis.filter(estaFora)
  const cartao = (c: Camera) => {
          const fora = estaFora(c)
          const img = urlDe(c)
          return (
            <article key={c.id} className={`vidro overflow-hidden ${c.ativo ? '' : 'opacity-60'}`}>
              {img ? (
                <button type="button" className="block w-full" onClick={() => setVer(Math.max(0, itens.findIndex((x) => x.id === c.id)))} aria-label={`Abrir a foto de ${c.nome}`}>
                  <img src={img} alt={c.nome} className="aspect-video w-full object-cover" />
                </button>
              ) : <div className="flex aspect-video items-center justify-center bg-slate-100 text-slate-400">sem imagem</div>}
              <div className="flex items-center justify-between gap-2 p-3">
                <div className="min-w-0 flex-1">
                  {editando === c.id ? (
                    <form className="flex items-center gap-1" onSubmit={(e) => { e.preventDefault(); void salvarApelido(c.id) }}>
                      <input autoFocus value={apelido} onChange={(e) => setApelido(e.target.value)} className="min-w-0 flex-1" placeholder="Ex.: Cozinha" />
                      <button className="pilula" aria-label="Salvar nome"><Check size={16} /></button>
                    </form>
                  ) : (
                    <h2 className="flex items-center gap-1.5 font-medium text-white">
                      <span className="truncate">{c.nome}</span>
                      {admin && (
                        <button type="button" aria-label="Renomear câmera" className="shrink-0 text-slate-400" onClick={() => { setEditando(c.id); setApelido(c.nome.startsWith('Câmera ') ? '' : c.nome) }}>
                          <Pencil size={13} />
                        </button>
                      )}
                      {c.ip_atual && <span className="shrink-0 text-[12px] font-normal text-slate-500">{c.ip_atual}</span>}
                    </h2>
                  )}
                  <p className="text-[12px] text-slate-500">
                    {c.foto_em ? `Foto de ${horaCompleta(c.foto_em)} (${haQuanto(c.foto_em)})` : 'Sem foto ainda'}
                  </p>
                  {c.ultimo_erro && fora && <p className="truncate text-[11px] text-rose-400">{c.ultimo_erro}</p>}
                </div>
                <span className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] font-bold ${fora ? 'bg-rose-500/15 text-rose-300' : 'bg-lime-300/10 text-lime-300'}`}>{fora ? 'Sem sinal' : 'Online'}</span>
              </div>
              <div className="flex gap-2 px-3 pb-3">
                <button className="pilula flex-1 justify-center !py-2 text-[13px]" disabled={!img} onClick={() => setVer(Math.max(0, itens.findIndex((x) => x.id === c.id)))}>
                  Abrir câmera
                </button>
                <button className="pilula flex-1 justify-center !py-2 text-[13px]" disabled={batendo === c.id || buscando} onClick={() => void pedirFotos(c.id)} aria-label={`Bater foto de ${c.nome}`}>
                  <CamIcon size={14} className={batendo === c.id ? 'animate-pulse' : ''} /> {batendo === c.id ? 'Batendo…' : 'Bater foto'}
                </button>
              </div>
            </article>
          )
  }

  return (
    <div className="space-y-3">
      {ver != null && itens[ver] && (
        <Visualizador
          itens={itens}
          indice={ver}
          onIndice={setVer}
          onFechar={() => setVer(null)}
          marcar={admin ? { opcoes: [...dados.pets.map((p) => ({ valor: `pet:${p.id}`, nome: p.nome, grupo: 'Quem é' })), ...dados.gente.map((g) => ({ valor: `pessoa:${g.id}`, nome: g.nome, grupo: 'Quem é' })), ...opcoesDeLocais(dados.pets)], onMarcar: marcarNaCamera, onApagarLocal: async (id) => { await supabase.from('pm_zonas').delete().eq('id', id); await recarregar() } } : undefined}
          acao={{ rotulo: 'Bater foto agora', ocupado: batendo === itens[ver].id, onClick: () => void pedirFotos(itens[ver].id) }}
        />
      )}
      <button className="botao-principal w-full sm:w-auto" disabled={buscando} onClick={() => void pedirFotos()}>
        <CamIcon size={16} className={buscando ? 'animate-pulse' : ''} /> {buscando ? 'Tirando fotos…' : 'Ver ao vivo'}
      </button>
      {msg && <p className="text-sm text-rose-400">{msg}</p>}
      {admin && visiveis.some((c) => c.nome.startsWith('Câmera ')) && (
        <p className="vidro px-3 py-2 text-[12px] text-slate-600">Câmeras novas foram achadas na rede. Olhe a imagem e toque no lápis para dar o nome do local (Cozinha, Quarto…).</p>
      )}
      {ocultas > 0 && <p className="text-[12px] text-slate-500">{ocultas} câmera(s) desativada(s) — reative em Ajustes.</p>}
      <div className="grid gap-4 sm:grid-cols-2">{online.map(cartao)}</div>
      {offline.length > 0 && (
        <details className="group">
          <summary className="flex cursor-pointer list-none items-center gap-2 rounded-full border border-white/10 bg-white/[0.06] px-4 py-2.5 text-sm font-medium text-white/85 hover:bg-white/10 [&::-webkit-details-marker]:hidden">
            <ChevronRight size={16} className="transition-transform group-open:rotate-90" />
            Sem sinal <span className="rounded-full bg-rose-500/15 px-2 py-0.5 text-[11px] font-medium text-rose-300">{offline.length}</span>
          </summary>
          <div className="mt-3 grid gap-4 sm:grid-cols-2">{offline.map(cartao)}</div>
        </details>
      )}
    </div>
  )
}
