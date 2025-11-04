import React, { useEffect, useState } from 'react'
import Chat from './components/Chat.jsx'
import Auth from './components/Auth.jsx'
import Profile from './components/Profile.jsx'
import Employees from './components/Employees.jsx'   // ← nuevo
import TopNav from './components/TopNav.jsx'
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
  if (!token) { window.alert('Debes iniciar sesión para guardar proyectos.'); return }
      const base = `http://${window.location.hostname}:8000`
  const payload = { title: title || `Proyecto ${new Date().toLocaleString()}`, content: JSON.stringify(messages) }
      try {
        await axios.post(`${base}/user/chats`, payload, { headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' } })
        await fetchChats()
      } catch (e) {
        if (!handleAuthError(e)) console.error('save chat', e)
      }
    } catch (e) { console.error('save chat', e) }
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
        setSessionIdForChat(sid)
        setView('chat')
      } catch (e) {
        if (!handleAuthError(e)) console.error('continue', e)
      }
    } catch (e) { console.error('continue', e) }
  }

  // Top navigation controls the visible section; Sidebar is only shown in Proyectos (view === 'chat')

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-emerald-50">
      <header className="border-b bg-white/80 backdrop-blur sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="font-semibold">Assistant · Propuestas</div>
          {token && (
            <TopNav
              current={view === 'employees' ? 'employees' : view === 'profile' ? 'profile' : 'projects'}
              onGoProjects={() => setView('chat')}
              onGoEmployees={() => setView('employees')}
              onGoProfile={() => setView('profile')}
              onLogout={logout}
            />
          )}
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-6">
        <div className="bg-white/70 backdrop-blur shadow-xl rounded-3xl p-4 flex h-[78vh] border">
          {!token ? (
            <div className="w-full grid place-items-center">
              <div className="w-full max-w-md"><Auth onLogin={onLogin} /></div>
            </div>
          ) : (
            <>
              {view === 'chat' && (
              <div className="w-80 flex-shrink-0 mr-4">
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

              <div className="flex-1">
                {view === 'profile' ? (
                  <Profile token={token} onOpenChat={(c) => { onSelectChat(c) }} logout={logout} />
                ) : view === 'employees' ? (
                  <Employees token={token} />
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
          )}
        </div>
      </main>
    </div>
  )
}
