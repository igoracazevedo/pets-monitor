import { createClient } from '@supabase/supabase-js'

const url = import.meta.env.VITE_SUPABASE_URL || 'https://kslmyvlewsmjnrhwklfd.supabase.co'
const chave = import.meta.env.VITE_SUPABASE_ANON_KEY || 'sb_publishable_WjgE2b2iKdZrRopbQieW3A_Cr9R9pGB'

export const supabase = createClient(url, chave)

export type Pet = { id: string; nome: string; especie: string; porte: string | null; descricao: string | null; perfil: unknown; ativo: boolean; precisa_reaprender: boolean; foto_perfil_path: string | null; notificar: boolean; cor?: string | null }
export type PetFoto = { id: string; pet_id: string; path: string }
export type Camera = {
  id: string
  nome: string
  ambiente: string | null
  ordem: number
  ativo: boolean
  ultima_leitura: string | null
  ultimo_status: string | null
  ultimo_erro: string | null
  ultimo_quadro_path: string | null
  foto_em: string | null
  ip_atual: string | null
}
export type Posicao = { pet_id: string; camera_id: string | null; visto_em: string; confianca: number | null; snapshot_path: string | null; foto_em: string | null; x: number | null; y: number | null; w: number | null; h: number | null }
export type Presenca = { camera_id: string; pessoas: number; ultima_vez: string | null; snapshot_path: string | null; foto_em: string | null; quem: string | null }
export type Pessoa = { id: string; nome: string; ativo: boolean; precisa_reaprender: boolean; notificar: boolean; cor?: string | null }
export type Zona = { id: string; camera_id: string; tipo: 'banheiro' | 'bebedouro' | 'comedouro' | 'cama'; pet_id: string | null; x: number; y: number; w: number; h: number; poligono?: [number, number][] | null }
export type Avistamento = {
  especie?: string | null
  pessoa_id?: string | null
  id: number
  pet_id: string | null
  camera_id: string
  visto_em: string
  confianca: number | null
  identificacao: string | null
  snapshot_path: string | null
  x: number | null
  y: number | null
  w: number | null
  h: number | null
}

/** Links assinados (as fotos ficam num bucket privado). */
export async function urlsDasFotos(caminhos: (string | null | undefined)[]): Promise<Record<string, string>> {
  const unicos = [...new Set(caminhos.filter((c): c is string => !!c))]
  if (unicos.length === 0) return {}
  const { data } = await supabase.storage.from('pm-snapshots').createSignedUrls(unicos, 3600)
  const out: Record<string, string> = {}
  for (const d of data ?? []) if (d.path && d.signedUrl) out[d.path] = d.signedUrl
  return out
}

const ehHeic = (a: File) => /hei[cf]/i.test(a.type) || /\.hei[cf]$/i.test(a.name)

/** Decodifica pelo elemento <img> (aceita casos em que createImageBitmap falha, ex.: arquivos grandes ou tipo desconhecido). */
async function viaImg(blob: Blob): Promise<ImageBitmap> {
  const url = URL.createObjectURL(blob)
  try {
    const img = new Image()
    img.src = url
    await img.decode()
    return await createImageBitmap(img)
  } finally {
    URL.revokeObjectURL(url)
  }
}

/** Abre qualquer foto: tenta o navegador (2 jeitos) e, se falhar, converte como HEIC/HEIF (iPhone/Samsung) para JPEG. */
async function abrirImagem(arquivo: File): Promise<ImageBitmap> {
  if (!ehHeic(arquivo)) {
    for (const abrir of [() => createImageBitmap(arquivo), () => viaImg(arquivo)]) {
      try {
        return await abrir()
      } catch {
        /* tenta o próximo */
      }
    }
  }
  try {
    const { heicTo } = await import('heic-to')
    const jpeg = await heicTo({ blob: arquivo, type: 'image/jpeg', quality: 0.9 })
    return await createImageBitmap(jpeg)
  } catch (e) {
    throw new Error(`Não consegui abrir a foto "${arquivo.name}" (${arquivo.type || 'tipo desconhecido'}, ${Math.round(arquivo.size / 1024)} KB). ${e instanceof Error ? e.message : ''}`)
  }
}

/** Reduz a foto (celular gera arquivos enormes) antes de enviar. */
export async function reduzirImagem(arquivo: File, lado = 1280): Promise<Blob> {
  const bmp = await abrirImagem(arquivo)
  const k = Math.min(1, lado / Math.max(bmp.width, bmp.height))
  const c = document.createElement('canvas')
  c.width = Math.round(bmp.width * k)
  c.height = Math.round(bmp.height * k)
  c.getContext('2d')!.drawImage(bmp, 0, 0, c.width, c.height)
  return await new Promise((ok, erro) => c.toBlob((b) => (b ? ok(b) : erro(new Error('imagem inválida'))), 'image/jpeg', 0.85))
}

/** Recorte quadrado central (foto de perfil). */
export async function recortarQuadrado(arquivo: File, lado = 512): Promise<Blob> {
  const bmp = await abrirImagem(arquivo)
  const m = Math.min(bmp.width, bmp.height)
  const c = document.createElement('canvas')
  c.width = c.height = lado
  c.getContext('2d')!.drawImage(bmp, (bmp.width - m) / 2, (bmp.height - m) / 2, m, m, 0, 0, lado, lado)
  return await new Promise((ok, erro) => c.toBlob((b) => (b ? ok(b) : erro(new Error('imagem inválida'))), 'image/jpeg', 0.88))
}

/** Links assinados do bucket de fotos de pets. */
export async function urlsDosPets(caminhos: (string | null | undefined)[]): Promise<Record<string, string>> {
  const unicos = [...new Set(caminhos.filter((c): c is string => !!c))]
  if (!unicos.length) return {}
  const { data } = await supabase.storage.from('pm-fotos-pets').createSignedUrls(unicos, 3600)
  const out: Record<string, string> = {}
  for (const d of data ?? []) if (d.path && d.signedUrl) out[d.path] = d.signedUrl
  return out
}

type Caixa = { x: number | null; y: number | null; w: number | null; h: number | null }

const iou = (a: Caixa, b: Caixa) => {
  const [ax, ay, aw, ah, bx, by, bw, bh] = [a.x, a.y, a.w, a.h, b.x, b.y, b.w, b.h].map((v) => Number(v ?? 0))
  const ix = Math.max(0, Math.min(ax + aw, bx + bw) - Math.max(ax, bx))
  const iy = Math.max(0, Math.min(ay + ah, by + bh) - Math.max(ay, by))
  const inter = ix * iy
  const uni = aw * ah + bw * bh - inter
  return uni > 0 ? inter / uni : 0
}

/**
 * "Não é pet": o detector passa a ignorar esse lugar na câmera (ex.: urso de pelúcia grande) e todos os registros
 * parecidos (mesma câmera, mesmo lugar) saem do histórico e da última posição. Devolve quantos registros foram apagados.
 */
export async function marcarComoObjeto(camera_id: string, x: number, y: number, w: number, h: number): Promise<number> {
  const alvo = { x, y, w, h }
  const ins = await supabase.from('pm_ignorar').insert({ camera_id, x, y, w, h })
  if (ins.error) throw new Error(ins.error.message)

  let apagados = 0
  const { data: regs } = await supabase.from('pm_avistamentos').select('id,x,y,w,h').eq('camera_id', camera_id).limit(5000)
  const ids = ((regs ?? []) as (Caixa & { id: number })[]).filter((r) => iou(r, alvo) > 0.4).map((r) => r.id)
  for (let i = 0; i < ids.length; i += 200) {
    const { error } = await supabase.from('pm_avistamentos').delete().in('id', ids.slice(i, i + 200))
    if (!error) apagados += Math.min(200, ids.length - i)
  }
  const { data: pos } = await supabase.from('pm_ultima_posicao').select('pet_id,x,y,w,h').eq('camera_id', camera_id)
  const pets = ((pos ?? []) as (Caixa & { pet_id: string })[]).filter((r) => iou(r, alvo) > 0.4).map((r) => r.pet_id)
  if (pets.length) await supabase.from('pm_ultima_posicao').delete().in('pet_id', pets)
  return apagados
}

export type EventoBanheiro = { id: string; camera_id: string; tipo: 'xixi' | 'coco' | 'limpo' | 'agua' | 'comeu'; pet_id: string | null; snapshot_path: string | null; visto_em: string }

export type ObjetoCatalogo = { id: string; zona_id: string | null; pet_id: string | null; tipo: Zona['tipo']; camera_origem: string | null; camera_id: string | null; imagem_path: string | null; sumido: boolean; visto_em: string | null }
