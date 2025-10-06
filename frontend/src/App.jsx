import React from 'react'
import Chat from './components/Chat.jsx'
import Auth from './components/Auth.jsx'
import Profile from './components/Profile.jsx'
import Sidebar from './components/Sidebar.jsx'
import axios from 'axios'
import { useState, useEffect } from 'react'

export default function App() {
  const [token, setToken] = useState(() => localStorage.getItem('tfg_token'))
  const logout = () => { localStorage.removeItem('tfg_token'); setToken(null) }
  const onLogin = (t) => { localStorage.setItem('tfg_token', t); setToken(t) }

  const [chats, setChats] = useState([])
  const [showProfile, setShowProfile] = useState(false)
  const [loadedMessages, setLoadedMessages] = useState(null)

  useEffect(()=>{
    if(token) fetchChats()
  }, [token])

  async function fetchChats(){
    try{
      const base = `http://${window.location.hostname}:8000`
      const res = await axios.get(`${base}/user/chats`, { headers: { Authorization: `Bearer ${token}` } })
      setChats(res.data)
    }catch(e){ console.error('fetch chats', e) }
  }

  const onSelectChat = (c) => {
    // load chat messages into Chat; content may be a JSON array or text
    try{
      const parsed = JSON.parse(c.content)
      setLoadedMessages(parsed)
    }catch(_){
      // assume plain text -> single assistant message
      setLoadedMessages([{ role: 'assistant', content: c.content, ts: c.updated_at }])
    }
    setShowProfile(false)
  }

  const onNew = () => { setLoadedMessages(null); setShowProfile(false) }
  const onProfile = () => setShowProfile(true)

  const onSaveCurrentChat = async (messages, title = null) => {
    // save messages as JSON string
    try{
      const base = `http://${window.location.hostname}:8000`
      const payload = { title: title || `Chat ${new Date().toLocaleString()}`, content: JSON.stringify(messages) }
      await axios.post(`${base}/user/chats`, payload, { headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' } })
      await fetchChats()
    }catch(e){ console.error('save chat', e) }
  }

  const onRename = async (chatId, newTitle) => {
    try{
      const base = `http://${window.location.hostname}:8000`
      await axios.put(`${base}/user/chats/${chatId}`, { title: newTitle, content: '' }, { headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' } })
      await fetchChats()
    }catch(e){ console.error('rename', e) }
  }

  const onDelete = async (chatId) => {
    try{
      const base = `http://${window.location.hostname}:8000`
      await axios.delete(`${base}/user/chats/${chatId}`, { headers: { Authorization: `Bearer ${token}` } })
      await fetchChats()
    }catch(e){ console.error('delete', e) }
  }

  const onContinue = async (chat) => {
    try{
      const base = `http://${window.location.hostname}:8000`
      const r = await axios.post(`${base}/user/chats/${chat.id}/continue`, {}, { headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' } })
      const sid = r.data.session_id
      // load messages
      try{ const parsed = JSON.parse(chat.content); setLoadedMessages(parsed) }catch(_){ setLoadedMessages([{ role: 'assistant', content: chat.content, ts: chat.updated_at }]) }
      setShowProfile(false)
      setSessionIdForChat(sid)
    }catch(e){ console.error('continue', e) }
  }

  // state to pass sessionId to Chat
  const [sessionIdForChat, setSessionIdForChat] = useState(null)

  return (
    <div className="min-h-screen bg-gray-50 p-4">
      <div className="max-w-6xl mx-auto bg-white shadow-lg rounded-2xl p-4 flex h-[80vh]">
        {!token ? (
          <div className="w-full">
            <Auth onLogin={onLogin} />
          </div>
        ) : (
          <>
            <div className="w-72 flex-shrink-0 mr-4">
              <Sidebar chats={chats} onSelect={onSelectChat} onNew={onNew} onProfile={onProfile} onRename={onRename} onDelete={onDelete} onContinue={onContinue} />
            </div>
            <div className="flex-1">
              {showProfile ? (
                <Profile token={token} onOpenChat={(c)=>{ onSelectChat(c); setShowProfile(false) }} logout={logout} />
              ) : (
                <Chat token={token} loadedMessages={loadedMessages} onSaveCurrentChat={onSaveCurrentChat} sessionId={sessionIdForChat} />
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
