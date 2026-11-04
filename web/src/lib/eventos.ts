import type { EventoBanheiro } from './supabase'

type Tipo = EventoBanheiro['tipo']

/** Exemplos ensinados pelo comando ("xixi no Banheiro") ficam em banheiro/ e não são ocorrências de verdade. */
export const exemplo = (e: EventoBanheiro) => !!e.snapshot_path?.startsWith('banheiro/')

const VERBO = { xixi: 'fez xixi', coco: 'fez cocô', agua: 'bebeu água', comeu: 'comendo' } as const
export function textoEvento(e: EventoBanheiro, nome: string | undefined): string {
  if (e.tipo === 'limpo') return 'Tapete limpo'
  if (nome) return `${nome} ${VERBO[e.tipo]}`
  if (e.tipo === 'comeu') return 'Uma das cachorras comendo'
  return e.tipo === 'agua' ? 'Uma das cachorras bebeu água' : `${e.tipo === 'coco' ? 'Cocô' : 'Xixi'} (não sei quem fez)`
}

/** Ordem fixa = ordem das cores da paleta validada (azul, laranja, verde-água, amarelo); a cor segue o tipo, não a posição. */
export const SERIES: { id: Tipo; nome: string; cor: string }[] = [
  { id: 'xixi', nome: 'Xixi', cor: '#2a78d6' },
  { id: 'coco', nome: 'Cocô', cor: '#eb6834' },
  { id: 'limpo', nome: 'Limpeza', cor: '#1baf7a' },
  { id: 'agua', nome: 'Água', cor: '#eda100' },
  { id: 'comeu', nome: 'Comida', cor: '#e87ba4' },
]
