import { useCallback, useEffect, useState, useSyncExternalStore } from 'react'

// Primeira carga da sessão: a tela de abertura espera todas as consultas que começaram juntas terminarem
let cargasAtivas = 0
let iniciou = false
let primeiraCargaFeita = false
const ouvintes = new Set<() => void>()
function avisar() {
  ouvintes.forEach((f) => f())
}
function cargaComecou() {
  iniciou = true
  cargasAtivas++
}
function cargaTerminou() {
  cargasAtivas = Math.max(0, cargasAtivas - 1)
  if (!primeiraCargaFeita && iniciou && cargasAtivas === 0) {
    // espera um instante: outras consultas da mesma tela podem estar começando
    setTimeout(() => {
      if (!primeiraCargaFeita && cargasAtivas === 0) {
        primeiraCargaFeita = true
        avisar()
      }
    }, 150)
  }
}
export const usePrimeiraCarga = () =>
  useSyncExternalStore(
    (f) => {
      ouvintes.add(f)
      // tela sem consultas: libera a abertura depois de um instante
      setTimeout(() => {
        if (!iniciou && !primeiraCargaFeita) {
          primeiraCargaFeita = true
          avisar()
        }
      }, 1500)
      return () => {
        ouvintes.delete(f)
      }
    },
    () => primeiraCargaFeita,
    () => false,
  )

/** Carrega e recarrega sozinho (a varredura grava a cada poucos segundos). */
export function useDados<T>(carregar: () => Promise<T>, inicial: T, cada = 15000) {
  const [dados, setDados] = useState<T>(inicial)
  const [erro, setErro] = useState<string | null>(null)
  const [carregando, setCarregando] = useState(true)
  const recarregar = useCallback(async () => {
    cargaComecou()
    try {
      setDados(await carregar())
      setErro(null)
    } catch (e) {
      setErro(e instanceof Error ? e.message : String(e))
    } finally {
      setCarregando(false)
      cargaTerminou()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  useEffect(() => {
    void recarregar()
    // aba escondida/tela apagada não precisa atualizar: poupa tráfego (volta a atualizar ao reabrir)
    const t = setInterval(() => {
      if (!document.hidden) void recarregar()
    }, cada)
    const aoVoltar = () => {
      if (!document.hidden) void recarregar()
    }
    document.addEventListener('visibilitychange', aoVoltar)
    return () => {
      clearInterval(t)
      document.removeEventListener('visibilitychange', aoVoltar)
    }
  }, [recarregar, cada])
  return { dados, erro, carregando, recarregar }
}
