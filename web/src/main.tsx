import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App'
import NovaVersao from './components/NovaVersao'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <NovaVersao />
    <App />
  </StrictMode>,
)
