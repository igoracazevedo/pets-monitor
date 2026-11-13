import { useCallback, useEffect, useState } from 'react'

/** Carrega e recarrega sozinho (a varredura grava a cada poucos segundos). */
export function useDados<T>(carregar: () => Promise<T>, inicial: T, cada = 15000) {
  const [dados, setDados] = useState<T>(inicial)
  const [erro, setErro] = useState<string | null>(null)
  const [carregando, setCarregando] = useState(true)
  const recarregar = useCallback(async () => {
    try {
      setDados(await carregar())
      setErro(null)
    } catch (e) {
      setErro(e instanceof Error ? e.message : String(e))
    } finally {
      setCarregando(false)
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
