import { useEffect, useState } from 'react'
import type { Session } from '@supabase/supabase-js'
import { Camera as CamIcon, Dog, History, PawPrint, Settings } from 'lucide-react'
import { supabase } from './lib/supabase'
import Inicio from './components/Inicio'
import Historico from './components/Historico'
import Cameras from './components/Cameras'
import Ajustes from './components/Ajustes'
import Pets from './components/Pets'
import { Carregando, Entrar, SemAcesso } from './components/Entrada'
import { Casca, type AbaDef } from './components/Casca'

const abas: AbaDef[] = [
  { id: 'inicio', nome: 'Início', Icone: PawPrint, ajuda: ['Cada cartão mostra a última câmera onde o pet foi visto e a foto daquele momento.', 'Toque em "Onde estão agora?" para o programa de casa olhar todas as câmeras na hora.'] },
  { id: 'historico', nome: 'Histórico', Icone: History, ajuda: ['Lista cada vez que um pet foi visto, com a câmera, a hora e a foto.', 'Use o filtro para ver só um pet ou os animais não identificados.'] },
  { id: 'cameras', nome: 'Câmeras', Icone: CamIcon, ajuda: ['"Ver ao vivo" tira uma foto nova de cada câmera e mostra a hora da captura.', 'Câmera nova aparece como "Câmera xxxx": toque no lápis e dê o nome do local.', 'Câmeras desativadas (em Ajustes) saem desta lista.'] },
  { id: 'pets', nome: 'Pets', Icone: Dog, ajuda: ['Cadastre cada pet, marque o porte (maior/menor da casa) e envie fotos dele sozinho.', 'Toque no quadradinho ao lado do nome para trocar a foto de perfil.', 'O programa de casa aprende com as fotos em até 2 minutos.'] },
  { id: 'ajustes', nome: 'Ajustes', Icone: Settings, ajuda: ['Ative ou desative câmeras.', 'Libere outros e-mails para acessar o app.'] },
]
type Aba = 'inicio' | 'historico' | 'cameras' | 'pets' | 'ajustes'

export default function App() {
  const [sessao, setSessao] = useState<Session | null | undefined>(undefined)
  const [acesso, setAcesso] = useState<{ membro: boolean; admin: boolean } | null>(null)
  const [aba, setAba] = useState<Aba>('inicio')

  useEffect(() => {
    void supabase.auth.getSession().then(({ data }) => setSessao(data.session))
    const { data } = supabase.auth.onAuthStateChange((_e, s) => setSessao(s))
    return () => data.subscription.unsubscribe()
  }, [])

  useEffect(() => {
    if (!sessao) return setAcesso(null)
    void Promise.all([supabase.rpc('pm_is_membro'), supabase.rpc('pm_is_admin')]).then(([m, a]) => setAcesso({ membro: m.data === true, admin: a.data === true }))
  }, [sessao])

  if (sessao === undefined) return <Carregando />
  if (!sessao) return <Entrar />
  if (!acesso) return <Carregando texto="Verificando acesso…" />
  if (!acesso.membro) return <SemAcesso email={sessao.user.email} />

  return (
    <Casca sessao={sessao} abas={abas} aba={aba} onAba={(id) => setAba(id as Aba)}>
      {aba === 'inicio' && <Inicio admin={acesso.admin} />}
      {aba === 'historico' && <Historico admin={acesso.admin} />}
      {aba === 'cameras' && <Cameras admin={acesso.admin} />}
      {aba === 'pets' && <Pets admin={acesso.admin} />}
      {aba === 'ajustes' && <Ajustes admin={acesso.admin} />}
    </Casca>
  )
}
