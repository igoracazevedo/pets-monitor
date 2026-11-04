import { supabase } from './supabase'
import type { Caixa } from '../components/Visualizador'

function carregarImagem(url: string): Promise<HTMLImageElement> {
  return new Promise((ok, erro) => {
    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.onload = () => ok(img)
    img.onerror = () => erro(new Error('imagem não carregou'))
    img.src = url
  })
}

/** Recorta o trecho marcado da foto (0 a 1) e devolve um JPEG + a largura da foto original. */
async function recortar(url: string, c: Caixa): Promise<{ blob: Blob; largura: number } | null> {
  const img = await carregarImagem(url)
  const W = img.naturalWidth, H = img.naturalHeight
  const x = Math.max(0, Math.round(c.x * W)), y = Math.max(0, Math.round(c.y * H))
  const w = Math.min(W - x, Math.round(c.w * W)), h = Math.min(H - y, Math.round(c.h * H))
  if (w < 8 || h < 8) return null
  const tela = document.createElement('canvas')
  tela.width = w
  tela.height = h
  tela.getContext('2d')!.drawImage(img, x, y, w, h, 0, 0, w, h)
  const blob = await new Promise<Blob | null>((ok) => tela.toBlob(ok, 'image/jpeg', 0.92))
  return blob ? { blob, largura: W } : null
}

/**
 * Marcar um local (banheiro, bebedouro, comedouro, cama) numa foto cria DUAS coisas:
 * o desenho na foto (pm_zonas) e o objeto do catálogo (pm_objetos), com o recorte desta foto guardado.
 * Apagar o desenho depois não apaga o objeto: ele só sai pela lista de Objetos.
 */
export async function marcarLocal(p: { cameraId: string; tipo: string; petId: string | null; caixa: Caixa; urlFoto?: string }) {
  const box = { x: Number(p.caixa.x.toFixed(4)), y: Number(p.caixa.y.toFixed(4)), w: Number(p.caixa.w.toFixed(4)), h: Number(p.caixa.h.toFixed(4)) }
  const z = await supabase.from('pm_zonas').insert({ camera_id: p.cameraId, tipo: p.tipo, pet_id: p.petId, ...box }).select('id').single()
  if (z.error) throw z.error
  const id = crypto.randomUUID()
  let imagem_path: string | null = null
  let largura_ref: number | null = null
  if (p.urlFoto) {
    try {
      const r = await recortar(p.urlFoto, p.caixa)
      if (r) {
        const caminho = `objetos/${id}.jpg`
        const up = await supabase.storage.from('pm-snapshots').upload(caminho, r.blob, { contentType: 'image/jpeg', upsert: true })
        if (!up.error) {
          imagem_path = caminho
          largura_ref = r.largura
        }
      }
    } catch {
      /* sem o recorte (foto bloqueada pelo navegador): o programa de casa aprende a aparência pela câmera */
    }
  }
  const o = await supabase.from('pm_objetos').insert({
    id, zona_id: z.data.id, pet_id: p.petId, tipo: p.tipo, camera_origem: p.cameraId, camera_id: p.cameraId, ...box, imagem_path, largura_ref, visto_em: new Date().toISOString(),
  })
  if (o.error) throw new Error(`O local foi marcado, mas o catálogo não gravou o objeto (${o.error.message}). Rode o SQL do catálogo no Supabase.`)
}
