import { createClient } from '@supabase/supabase-js'

const url = import.meta.env.VITE_SUPABASE_URL || 'https://kslmyvlewsmjnrhwklfd.supabase.co'
const chave = import.meta.env.VITE_SUPABASE_ANON_KEY || 'sb_publishable_WjgE2b2iKdZrRopbQieW3A_Cr9R9pGB'

export const supabase = createClient(url, chave)

export type Pet = { id: string; nome: string; especie: string; porte: string | null; descricao: string | null; perfil: unknown; ativo: boolean; precisa_reaprender: boolean; foto_perfil_path: string | null }
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
}
export type Posicao = { pet_id: string; camera_id: string | null; visto_em: string; confianca: number | null; snapshot_path: string | null }
export type Avistamento = {
  id: number
  pet_id: string | null
  camera_id: string
  visto_em: string
  confianca: number | null
  identificacao: string | null
  snapshot_path: string | null
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

/** Abre qualquer foto: HEIC/HEIF (iPhone) é convertido para JPEG no navegador antes de decodificar. */
async function abrirImagem(arquivo: File): Promise<ImageBitmap> {
  if (!ehHeic(arquivo)) {
    try {
      return await createImageBitmap(arquivo)
    } catch {
      /* formato que o navegador não lê: tenta como HEIC */
    }
  }
  const { heicTo } = await import('heic-to')
  const jpeg = await heicTo({ blob: arquivo, type: 'image/jpeg', quality: 0.9 })
  return await createImageBitmap(jpeg)
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
