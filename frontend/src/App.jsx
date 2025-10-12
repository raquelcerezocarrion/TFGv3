import React, { useEffect, useState } from 'react'
import Chat from './components/Chat.jsx'
import Auth from './components/Auth.jsx'
import Profile from './components/Profile.jsx'
import Sidebar from './components/Sidebar.jsx'
import axios from 'axios'

export default function App() {
  const [token, setToken] = useState(() => localStorage.getItem('tfg_token'))
  const logout = () => { localStorage.removeItem('tfg_token'); setToken(null) }
  const onLogin = (t) => { localStorage.setItem('tfg_token', t); setToken(t) }

  const [chats, setChats] = useState([])
  const [showProfile, setShowProfile] = useState(false)
  const [loadedMessages, setLoadedMessages] = useState(null)
  const [sessionIdForChat, setSessionIdForChat] = useState(null)

  useEffect(() => { if (token) fetchChats() }, [token])

  async function fetchChats() {
    try {
      const base = `http://${window.location.hostname}:8000`
      const res = await axios.get(`${base}/user/chats`, { headers: { Authorization: `Bearer ${token}` } })
      setChats(res.data)
    } catch (e) { console.error('fetch chats', e) }
  }

  const onSelectChat = (c) => {
    try { setLoadedMessages(JSON.parse(c.content)) }
    catch { setLoadedMessages([{ role: 'assistant', content: c.content, ts: c.updated_at }]) }
    setShowProfile(false)
  }
  const onNew = () => { setLoadedMessages(null); setShowProfile(false) }
  const onProfile = () => setShowProfile(true)

  const onSaveCurrentChat = async (messages, title = null) => {
    try {
      const base = `http://${window.location.hostname}:8000`
      const payload = { title: title || `Chat ${new Date().toLocaleString()}`, content: JSON.stringify(messages) }
      await axios.post(`${base}/user/chats`, payload, { headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' } })
      await fetchChats()
    } catch (e) { console.error('save chat', e) }
  }

  const onRename = async (chatId, newTitle) => {
    try {
      const base = `http://${window.location.hostname}:8000`
      await axios.put(`${base}/user/chats/${chatId}`, { title: newTitle, content: '' }, { headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' } })
      await fetchChats()
    } catch (e) { console.error('rename', e) }
  }

  const onDelete = async (chatId) => {
    try {
      const base = `http://${window.location.hostname}:8000`
      await axios.delete(`${base}/user/chats/${chatId}`, { headers: { Authorization: `Bearer ${token}` } })
      await fetchChats()
    } catch (e) { console.error('delete', e) }
  }

  const onContinue = async (chat) => {
    try {
      const base = `http://${window.location.hostname}:8000`
      const r = await axios.post(`${base}/user/chats/${chat.id}/continue`, {}, { headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' } })
      const sid = r.data.session_id
      try { setLoadedMessages(JSON.parse(chat.content)) }
      catch { setLoadedMessages([{ role: 'assistant', content: chat.content, ts: chat.updated_at }]) }
      setShowProfile(false)
      setSessionIdForChat(sid)
    } catch (e) { console.error('continue', e) }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-emerald-50">
      {/* Topbar minimalista */}
      <header className="border-b bg-white/80 backdrop-blur sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="font-semibold">Assistant · Propuestas</div>
          {token && (
            <button className="text-sm text-gray-600 hover:text-gray-800" onClick={() => setShowProfile(v => !v)}>
              {showProfile ? 'Volver al chat' : 'Mi perfil'}
            </button>
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
              <div className="w-80 flex-shrink-0 mr-4">
                <Sidebar
                  chats={chats}
                  onSelect={onSelectChat}
                  onNew={onNew}
                  onProfile={onProfile}
                  onRename={onRename}
                  onDelete={onDelete}
                  onContinue={onContinue}
                />
              </div>
              <div className="flex-1">
                {showProfile ? (
                  <Profile token={token} onOpenChat={(c) => { onSelectChat(c); setShowProfile(false) }} logout={logout} />
                ) : (
                  <Chat token={token} loadedMessages={loadedMessages} onSaveCurrentChat={onSaveCurrentChat} sessionId={sessionIdForChat} />
                )}
              </div>
            </>
          )}
        </div>
      </main>
    </div>
  )
}
