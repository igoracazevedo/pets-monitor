// Links de leitura das fotos pelo Cloudflare R2 (sem cobrança de tráfego), com o Supabase como origem.
// POST { bucket, caminhos: [..] } com "Authorization: Bearer <token do Supabase>" (membro do app, pm_is_membro).
// Para cada caminho: se o arquivo já está no R2, devolve o link; senão copia do Supabase (com o login de quem pediu)
// para o R2 e devolve o link. Quem não conseguir (R2 fora do ar, arquivo ausente) volta null e o app usa o link do Supabase.
import { configR2, existe, gravar, urlLeitura } from './_r2.js'

const SUPABASE_URL = process.env.SUPABASE_URL || process.env.VITE_SUPABASE_URL || 'https://kslmyvlewsmjnrhwklfd.supabase.co'
const ANON = process.env.SUPABASE_ANON_KEY || process.env.VITE_SUPABASE_ANON_KEY || 'sb_publishable_WjgE2b2iKdZrRopbQieW3A_Cr9R9pGB'
const BUCKETS = ['pm-snapshots', 'pm-fotos-pets']
// arquivos sobrescritos no mesmo caminho (quadro ao vivo da câmera) nunca vão para o R2
const MUTAVEL = (p) => p.startsWith('cameras/') || p.startsWith('ao-vivo/')
const PRAZO_MS = 22_000

const cfg = () => configR2({ ...process.env, R2_BUCKET: process.env.R2_BUCKET || 'pets-monitor' })
const codificar = (p) => p.split('/').map(encodeURIComponent).join('/')

async function copiar(c, token, bucket, caminho) {
  const objeto = `${bucket}/${caminho}`
  if (!(await existe(c, objeto))) {
    const r = await fetch(`${SUPABASE_URL}/storage/v1/object/authenticated/${bucket}/${codificar(caminho)}`, {
      headers: { apikey: ANON, Authorization: `Bearer ${token}` },
      signal: AbortSignal.timeout(15_000),
    })
    if (!r.ok) throw new Error(`Supabase ${r.status}`)
    await gravar(c, objeto, Buffer.from(await r.arrayBuffer()), r.headers.get('content-type') || 'application/octet-stream')
  }
  return urlLeitura(c, objeto)
}

export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).json({ erro: 'Método inválido' })
  const c = cfg()
  if (!c) return res.status(503).json({ erro: 'R2 não configurado' })
  try {
    const token = (req.headers.authorization || '').replace(/^Bearer /, '')
    if (!token) return res.status(401).json({ erro: 'Sem login' })
    const u = await fetch(`${SUPABASE_URL}/auth/v1/user`, { headers: { apikey: ANON, Authorization: `Bearer ${token}` } })
    if (!u.ok) return res.status(401).json({ erro: 'Login inválido' })
    const m = await fetch(`${SUPABASE_URL}/rest/v1/rpc/pm_is_membro`, { method: 'POST', headers: { apikey: ANON, Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, body: '{}' })
    if (!m.ok || (await m.json()) !== true) return res.status(403).json({ erro: 'Sem acesso' })

    const { bucket, caminhos } = req.body || {}
    if (!BUCKETS.includes(bucket) || !Array.isArray(caminhos)) return res.status(400).json({ erro: 'bucket ou caminhos inválidos' })
    const lista = [...new Set(caminhos.filter((p) => typeof p === 'string' && p && !p.includes('..') && !MUTAVEL(p)))].slice(0, 120)

    const urls = {}
    const fim = Date.now() + PRAZO_MS
    let i = 0
    await Promise.all(
      Array.from({ length: 6 }, async () => {
        while (i < lista.length && Date.now() < fim) {
          const p = lista[i++]
          try {
            urls[p] = await copiar(c, token, bucket, p)
          } catch (e) {
            console.warn('foto-url:', p, e?.message)
            urls[p] = null
          }
        }
      }),
    )
    for (const p of lista) if (!(p in urls)) urls[p] = null
    return res.status(200).json({ urls })
  } catch (e) {
    console.error('foto-url: erro', e)
    return res.status(500).json({ erro: 'Falha ao gerar links' })
  }
}
