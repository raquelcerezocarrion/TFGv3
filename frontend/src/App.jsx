import React, { useEffect, useState } from 'react'
import Chat from './components/Chat.jsx'
import Auth from './components/Auth.jsx'
import Profile from './components/Profile.jsx'
import Employees from './components/Employees.jsx'   // ← nuevo
import TopNav from './components/TopNav.jsx'
import Recommendations from './components/Recommendations.jsx'
import Aprender from './components/Aprender.jsx'
import Sidebar from './components/Sidebar.jsx'
import axios from 'axios'

export default function App() {
  const [token, setToken] = useState(() => localStorage.getItem('tfg_token'))
  const logout = () => { localStorage.removeItem('tfg_token'); setToken(null) }
  const onLogin = (t) => { localStorage.setItem('tfg_token', t); setToken(t) }

  const [chats, setChats] = useState([])
  const [view, setView] = useState('chat') // 'chat' (Proyectos) | 'profile' | 'employees'
  const [loadedMessages, setLoadedMessages] = useState(null)
  const [selectedChatId, setSelectedChatId] = useState(null)
  const [sessionIdForChat, setSessionIdForChat] = useState(null)
  

  useEffect(() => { if (token) fetchChats() }, [token])

  async function fetchChats() {
    try {
      const base = `http://${window.location.hostname}:8000`
      const res = await axios.get(`${base}/user/chats`, { headers: { Authorization: `Bearer ${token}` } })
      setChats(res.data)
    } catch (e) {
      if (!handleAuthError(e)) console.error('fetch chats', e)
    }
  }

  function handleAuthError(e) {
    const status = e?.response?.status
    if (status === 401) {
      // token inválido/expirado: limpiar y forzar re-login
      localStorage.removeItem('tfg_token')
      setToken(null)
      window.alert('Sesión inválida. Por favor inicia sesión de nuevo.')
      return true
    }
    return false
  }

  const onSelectChat = (c) => {
    try { setLoadedMessages(JSON.parse(c.content)) }
    catch { setLoadedMessages([{ role: 'assistant', content: c.content, ts: c.updated_at }]) }
    setSelectedChatId(c.id)
    setView('chat')
  }
  const onNew = async () => {
    // Pedimos título al usuario y creamos un chat vacío en backend para
    // que aparezca inmediatamente en la lista de chats guardados.
    try {
      if (!token) {
        // prevenimos intentos anónimos; el backend devuelve 401 si no hay token
        window.alert('Debes iniciar sesión para crear un proyecto.')
        return
      }
      const title = window.prompt('Título del proyecto:', 'Nuevo proyecto')
      if (title === null) return // usuario canceló
      const base = `http://${window.location.hostname}:8000`
      // El endpoint exige 'content' no vacío; usamos un array JSON vacío como contenido inicial
      const payload = { title: title || `Proyecto ${new Date().toLocaleString()}`, content: JSON.stringify([]) }
      let res
      try {
        res = await axios.post(`${base}/user/chats`, payload, { headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' } })
        await fetchChats()
      } catch (e) {
        if (handleAuthError(e)) return; else throw e
      }
      // Abrir el chat recién creado si el backend devolvió la fila
      if (res && res.data) {
        try { setLoadedMessages(JSON.parse(res.data.content)) } catch { setLoadedMessages([]) }
        setSelectedChatId(res.data.id)
      } else {
        setLoadedMessages([])
        setSelectedChatId(null)
      }
      setView('chat')
    } catch (e) { console.error('new project', e) }
  }
  const onProfile   = () => setView('profile')
  const onEmployees = () => setView('employees')
  

  const onSaveCurrentChat = async (messages, title = null) => {
    try {
  if (!token) { window.alert('Debes iniciar sesión para guardar proyectos.'); return null }
      const base = `http://${window.location.hostname}:8000`
  const payload = { title: title || `Proyecto ${new Date().toLocaleString()}`, content: JSON.stringify(messages) }
      try {
        const res = await axios.post(`${base}/user/chats`, payload, { headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' } })
        const newChatId = res.data?.id || null
        await fetchChats()
        // También actualizamos selectedChatId para que esté disponible
        if (newChatId) setSelectedChatId(newChatId)
        return newChatId
      } catch (e) {
        if (!handleAuthError(e)) console.error('save chat', e)
        return null
      }
    } catch (e) { console.error('save chat', e); return null }
  }

  const onSaveExistingChat = async (chatId, messages, title = null) => {
    try {
  if (!token) { window.alert('Debes iniciar sesión para guardar cambios.'); return }
      const base = `http://${window.location.hostname}:8000`
      const body = { content: JSON.stringify(messages) }
      if (title) body.title = title
      try {
        await axios.put(`${base}/user/chats/${chatId}`, body, { headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' } })
        await fetchChats()
      } catch (e) {
        if (!handleAuthError(e)) console.error('save existing', e)
      }
    } catch (e) { console.error('save existing', e) }
  }

  const onRename = async (chatId, newTitle) => {
    try {
  if (!token) { window.alert('Debes iniciar sesión para renombrar proyectos.'); return }
      const base = `http://${window.location.hostname}:8000`
      // Enviar solo el título para evitar sobreescribir el contenido con cadena vacía
      try {
        await axios.put(`${base}/user/chats/${chatId}`, { title: newTitle }, { headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' } })
        await fetchChats()
      } catch (e) {
        if (!handleAuthError(e)) console.error('rename', e)
      }
    } catch (e) { console.error('rename', e) }
  }

  const onDelete = async (chatId) => {
    try {
  if (!token) { window.alert('Debes iniciar sesión para eliminar proyectos.'); return }
      const base = `http://${window.location.hostname}:8000`
      try {
        await axios.delete(`${base}/user/chats/${chatId}`, { headers: { Authorization: `Bearer ${token}` } })
        await fetchChats()
      } catch (e) {
        if (!handleAuthError(e)) console.error('delete', e)
      }
    } catch (e) { console.error('delete', e) }
  }

  const onContinue = async (chat) => {
    try {
  if (!token) { window.alert('Debes iniciar sesión para continuar proyectos.'); return }
      const base = `http://${window.location.hostname}:8000`
      try {
        const r = await axios.post(`${base}/user/chats/${chat.id}/continue`, {}, { headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' } })
        const sid = r.data.session_id
        try { setLoadedMessages(JSON.parse(chat.content)) }
        catch { setLoadedMessages([{ role: 'assistant', content: chat.content, ts: chat.updated_at }]) }
        setSelectedChatId(chat.id)
        setSessionIdForChat(sid)
        setView('chat')
      } catch (e) {
        if (!handleAuthError(e)) console.error('continue', e)
      }
    } catch (e) { console.error('continue', e) }
  }

  // Top navigation controls the visible section; Sidebar is only shown in Proyectos (view === 'chat')

  return (
    <div className="h-screen bg-gradient-to-br from-slate-800 via-blue-900 to-indigo-900 relative overflow-hidden">
      {/* Patrón de cuadrícula sutil */}
      <div className="absolute inset-0 z-0" style={{
        backgroundImage: `
          linear-gradient(to right, rgba(255,255,255,0.03) 1px, transparent 1px),
          linear-gradient(to bottom, rgba(255,255,255,0.03) 1px, transparent 1px)
        `,
        backgroundSize: '40px 40px'
      }}></div>
      
      {/* Círculos decorativos sutiles */}
      <div className="absolute -top-40 -left-40 w-96 h-96 bg-blue-500/10 rounded-full blur-3xl z-0"></div>
      <div className="absolute -bottom-40 -right-40 w-[600px] h-[600px] bg-indigo-500/10 rounded-full blur-3xl z-0"></div>
      <div className="absolute top-1/3 -right-20 w-80 h-80 bg-slate-400/8 rounded-full blur-2xl z-0"></div>
      
      <div className="relative z-10">
              <header className="bg-transparent backdrop-blur-md sticky top-0 z-20" role="banner" aria-label="Main banner">
                <div className="px-6 py-4 flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-gradient-to-br from-blue-600 to-indigo-700 rounded-lg flex items-center justify-center text-white text-xl shadow-lg">
                      🎯
                    </div>
                    <h1 className="text-2xl font-bold text-white drop-shadow-lg">
                      Asistente de consultoría estratégica
                    </h1>
                  </div>
                {token && (
            <TopNav
              current={view === 'employees' ? 'employees' : view === 'profile' ? 'profile' : (view === 'recommendations' ? 'recommendations' : (view === 'aprender' ? 'aprender' : 'projects'))}
              onGoProjects={() => setView('chat')}
              onGoAprender={() => setView('aprender')}
              onGoRecommendations={() => setView('recommendations')}
              onGoEmployees={() => setView('employees')}
              onGoProfile={() => setView('profile')}
              onLogout={logout}
            />
          )}
        </div>
      </header>

      <main className="w-full h-[calc(100vh-64px)] overflow-hidden p-4" role="main" aria-label="Main content">
        <div className="bg-transparent flex h-full w-full">
          {!token ? (
            <Auth onLogin={onLogin} />
          ) : (
            <div className="bg-white/95 backdrop-blur-xl shadow-2xl rounded-2xl flex h-full w-full border border-white/30 overflow-hidden">
            <>
              {view === 'chat' && (
              <div className="w-80 flex-shrink-0 mr-4 p-4">
                <Sidebar
                  chats={chats}
                  onSelect={onSelectChat}
                  onNew={onNew}
                  onRename={onRename}
                  onDelete={onDelete}
                  onContinue={onContinue}
                />
              </div>
              )}

              <div className="flex-1 overflow-hidden p-4">
                {view === 'profile' ? (
                  <Profile token={token} onOpenChat={(c) => { onSelectChat(c) }} logout={logout} />
                ) : view === 'employees' ? (
                  <Employees token={token} />
                ) : view === 'aprender' ? (
                  <Aprender token={token} />
                ) : view === 'recommendations' ? (
                  <Recommendations token={token} />
                ) : (
                  <Chat
                    token={token}
                    loadedMessages={loadedMessages}
                    selectedChatId={selectedChatId}
                    onSaveCurrentChat={onSaveCurrentChat}
                    onSaveExistingChat={onSaveExistingChat}
                    sessionId={sessionIdForChat}
                  />
                )}
              </div>
            </>
            </div>
          )}
        </div>
      </main>
      </div>
    </div>
  )
}
