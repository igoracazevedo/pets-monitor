import { supabase } from './supabase'

// Chave pública do aviso (não é segredo). A privada fica só no .env do PC de casa.
const CHAVE_PUBLICA = import.meta.env.VITE_VAPID_PUBLIC_KEY || 'BFS3Yh9YGRlM4nLGKw3Yap66iIr1SHyW8xZcILXRAMuAVC7pai_g9IfgB0k8IRVmjToaN4bs0ichPciub-yNT0Y'

const paraBytes = (b64: string) => {
  const pad = '='.repeat((4 - (b64.length % 4)) % 4)
  const raw = atob((b64 + pad).replace(/-/g, '+').replace(/_/g, '/'))
  return Uint8Array.from(raw, (c) => c.charCodeAt(0))
}

export const suportaAvisos = () => 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window

export async function registrarServiceWorker() {
  if ('serviceWorker' in navigator) {
    try {
      await navigator.serviceWorker.register('/sw.js')
    } catch {
      /* sem service worker não há aviso, mas o app funciona */
    }
  }
}

export async function avisosAtivos(): Promise<boolean> {
  if (!suportaAvisos()) return false
  const reg = await navigator.serviceWorker.getRegistration()
  return !!(reg && (await reg.pushManager.getSubscription()))
}

/** Pede permissão, assina o aparelho e guarda a assinatura no Supabase (só do próprio usuário). */
export async function ativarAvisos(email: string): Promise<void> {
  if (!suportaAvisos()) throw new Error('Este navegador não suporta avisos. No iPhone, instale o app na Tela de Início primeiro.')
  if ((await Notification.requestPermission()) !== 'granted') throw new Error('A permissão de avisos foi negada nas configurações do navegador.')
  const reg = (await navigator.serviceWorker.getRegistration()) ?? (await navigator.serviceWorker.register('/sw.js'))
  await navigator.serviceWorker.ready
  const sub = (await reg.pushManager.getSubscription()) ?? (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: paraBytes(CHAVE_PUBLICA) }))
  const { error } = await supabase.from('pm_push').upsert({ endpoint: sub.endpoint, email: email.toLowerCase(), assinatura: sub.toJSON() })
  if (error) throw new Error(error.message)
}

export async function desativarAvisos(): Promise<void> {
  const reg = await navigator.serviceWorker.getRegistration()
  const sub = await reg?.pushManager.getSubscription()
  if (sub) {
    await supabase.from('pm_push').delete().eq('endpoint', sub.endpoint)
    await sub.unsubscribe()
  }
}
