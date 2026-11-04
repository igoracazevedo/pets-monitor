import { corPadraoPet, corValida } from './cores'
import type { Pet, Zona } from './supabase'
import type { Local, Opcao } from '../components/Visualizador'

export const TIPOS_ZONA = { banheiro: 'Banheiro', bebedouro: 'Bebedouro', comedouro: 'Comedouro', cama: 'Cama' } as const

export function corDoPet(pets: Pet[], id: string | null): string {
  const i = pets.findIndex((p) => p.id === id)
  return i < 0 ? '#9ca3af' : corValida(pets[i].cor) ? pets[i].cor! : corPadraoPet(i)
}

export const rotuloZona = (pets: Pet[], z: Zona) => `${TIPOS_ZONA[z.tipo]} ${z.pet_id ? `da ${pets.find((p) => p.id === z.pet_id)?.nome ?? '?'}` : '(das duas)'}`

export function locaisDaCamera(pets: Pet[], zonas: Zona[], cameraId: string): Local[] {
  return zonas.filter((z) => z.camera_id === cameraId).map((z) => ({ id: z.id, caixa: { x: Number(z.x), y: Number(z.y), w: Number(z.w), h: Number(z.h) }, rotulo: rotuloZona(pets, z), cor: corDoPet(pets, z.pet_id) }))
}

/** Opções do "Marcar quem é" para marcar locais (banheiro, bebedouro, comedouro, cama) de cada pet ou das duas. */
export function opcoesDeLocais(pets: Pet[]): Opcao[] {
  return (Object.keys(TIPOS_ZONA) as (keyof typeof TIPOS_ZONA)[]).flatMap((t) => [
    ...pets.map((p) => ({ valor: `zona:${t}:${p.id}`, nome: `${TIPOS_ZONA[t]} da ${p.nome}`, grupo: 'Marcar local' })),
    { valor: `zona:${t}:todos`, nome: `${TIPOS_ZONA[t]} (das duas)`, grupo: 'Marcar local' },
  ])
}
