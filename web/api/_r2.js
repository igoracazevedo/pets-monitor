// Cloudflare R2 (compatível com S3) sem dependências: assinatura AWS SigV4 feita com o crypto do Node.
// Usado como cache de leitura das fotos: o 1º acesso copia o arquivo do Supabase para o R2 e os próximos saem do R2 (sem cobrança de tráfego).
import { createHash, createHmac } from 'node:crypto'

const sha256 = (d) => createHash('sha256').update(d).digest('hex')
const hmac = (k, d) => createHmac('sha256', k).update(d).digest()
const enc = (s) => encodeURIComponent(s).replace(/[!'()*]/g, (c) => '%' + c.charCodeAt(0).toString(16).toUpperCase())

export function configR2(env = process.env) {
  const conta = env.R2_ACCOUNT_ID, chave = env.R2_ACCESS_KEY_ID, segredo = env.R2_SECRET_ACCESS_KEY, bucket = env.R2_BUCKET
  if (!conta || !chave || !segredo || !bucket) return null
  return { host: `${conta}.r2.cloudflarestorage.com`, chave, segredo, bucket }
}

const caminhoDe = (cfg, objeto) => `/${cfg.bucket}/${objeto.split('/').map(enc).join('/')}`
const chaveDeAssinatura = (cfg, dia) => hmac(hmac(hmac(hmac('AWS4' + cfg.segredo, dia), 'auto'), 's3'), 'aws4_request')
const stamp = (agora) => agora.toISOString().replace(/[:-]|\.\d{3}/g, '')

/** URL temporária de leitura (GET) de um objeto. */
export function urlLeitura(cfg, objeto, { expira = 8 * 3600, agora = new Date(), cache = 'private, max-age=31536000, immutable', extra = {} } = {}) {
  const t = stamp(agora), dia = t.slice(0, 8)
  const escopo = `${dia}/auto/s3/aws4_request`
  const q = {
    'X-Amz-Algorithm': 'AWS4-HMAC-SHA256',
    'X-Amz-Credential': `${cfg.chave}/${escopo}`,
    'X-Amz-Date': t,
    'X-Amz-Expires': String(expira),
    'X-Amz-SignedHeaders': 'host',
    ...(cache ? { 'response-cache-control': cache } : {}),
    ...extra,
  }
  const consulta = Object.keys(q).sort().map((k) => `${enc(k)}=${enc(q[k])}`).join('&')
  const caminho = caminhoDe(cfg, objeto)
  const canonico = ['GET', caminho, consulta, `host:${cfg.host}\n`, 'host', 'UNSIGNED-PAYLOAD'].join('\n')
  const assinar = ['AWS4-HMAC-SHA256', t, escopo, sha256(canonico)].join('\n')
  const assinatura = createHmac('sha256', chaveDeAssinatura(cfg, dia)).update(assinar).digest('hex')
  return `https://${cfg.host}${caminho}?${consulta}&X-Amz-Signature=${assinatura}`
}

/** Cabeçalhos assinados (SigV4) de um pedido HEAD/PUT. */
export function cabecalhosAssinados(cfg, metodo, objeto, corpo, tipo, agora = new Date()) {
  const t = stamp(agora), dia = t.slice(0, 8)
  const escopo = `${dia}/auto/s3/aws4_request`
  const hash = sha256(corpo ?? '')
  const cab = { host: cfg.host, 'x-amz-content-sha256': hash, 'x-amz-date': t, ...(tipo ? { 'content-type': tipo } : {}) }
  const nomes = Object.keys(cab).sort()
  const canonico = [metodo, caminhoDe(cfg, objeto), '', nomes.map((n) => `${n}:${cab[n]}\n`).join(''), nomes.join(';'), hash].join('\n')
  const assinar = ['AWS4-HMAC-SHA256', t, escopo, sha256(canonico)].join('\n')
  const assinatura = createHmac('sha256', chaveDeAssinatura(cfg, dia)).update(assinar).digest('hex')
  const { host, ...resto } = cab
  return { ...resto, Authorization: `AWS4-HMAC-SHA256 Credential=${cfg.chave}/${escopo}, SignedHeaders=${nomes.join(';')}, Signature=${assinatura}` }
}

async function pedir(cfg, metodo, objeto, corpo, tipo) {
  return fetch(`https://${cfg.host}${caminhoDe(cfg, objeto)}`, {
    method: metodo,
    headers: cabecalhosAssinados(cfg, metodo, objeto, corpo, tipo),
    body: corpo ?? undefined,
    signal: AbortSignal.timeout(15_000),
  })
}

export async function existe(cfg, objeto) {
  const r = await pedir(cfg, 'HEAD', objeto)
  if (r.status === 404) return false
  if (!r.ok) throw new Error(`R2 HEAD ${r.status}`)
  return true
}

export async function gravar(cfg, objeto, corpo, tipo) {
  const r = await pedir(cfg, 'PUT', objeto, corpo, tipo)
  if (!r.ok) throw new Error(`R2 PUT ${r.status} ${(await r.text()).slice(0, 120)}`)
}
