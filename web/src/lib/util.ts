export function haQuanto(iso: string | null | undefined, agora = Date.now()): string {
  if (!iso) return 'nunca'
  const s = Math.max(0, Math.round((agora - new Date(iso).getTime()) / 1000))
  if (s < 60) return 'agora há pouco'
  const m = Math.round(s / 60)
  if (m < 60) return `há ${m} min`
  const h = Math.floor(m / 60)
  if (h < 24) return `há ${h} h ${m % 60 ? `${m % 60} min` : ''}`.trim()
  const d = Math.floor(h / 24)
  return `há ${d} ${d === 1 ? 'dia' : 'dias'}`
}

export function dataHora(iso: string): string {
  return new Date(iso).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
}

export const minutosDesde = (iso: string | null | undefined) => (iso ? (Date.now() - new Date(iso).getTime()) / 60000 : Infinity)
