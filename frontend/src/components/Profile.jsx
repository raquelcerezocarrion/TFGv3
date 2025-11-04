import React, { useEffect, useState } from 'react'
import axios from 'axios'

export default function Profile({ token, onOpenChat, logout }){
  const [apiBase, setApiBase] = useState(`http://${window.location.hostname}:8000`)
  const [profile, setProfile] = useState(null)
  const [chats, setChats] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [editing, setEditing] = useState(null)
  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')

  useEffect(()=>{ if(token) fetchProfileAndChats() }, [token])

  const authHeader = token ? { Authorization: `Bearer ${token}` } : {}

  async function fetchProfileAndChats(){
    setLoading(true); setError(null)
    try{
      const p = await axios.get(`${apiBase}/user/me`, { headers: { ...authHeader } })
      setProfile(p.data)
      const r = await axios.get(`${apiBase}/user/chats`, { headers: { ...authHeader } })
      setChats(r.data)
    }catch(e){ setError(e?.response?.data || e.message) }
    finally{ setLoading(false) }
  }

  async function saveChat(){
    setLoading(true); setError(null)
    try{
      if(editing){
        const r = await axios.put(`${apiBase}/user/chats/${editing}`, { title, content }, { headers: { ...authHeader, 'Content-Type': 'application/json' } })
        // update locally
        setChats(cs => cs.map(c => c.id === r.data.id ? r.data : c))
      } else {
        const r = await axios.post(`${apiBase}/user/chats`, { title, content }, { headers: { ...authHeader, 'Content-Type': 'application/json' } })
        setChats(cs => [r.data, ...cs])
      }
      setEditing(null); setTitle(''); setContent('')
    }catch(e){ setError(e?.response?.data || e.message) }
    finally{ setLoading(false) }
  }

  function editOne(c){ setEditing(c.id); setTitle(c.title||''); setContent(c.content||'') }

  return (
    <div className="p-4">
      <h2 className="text-lg font-semibold mb-2">Mi perfil</h2>
      {loading && <div>cargando…</div>}
      {error && <pre className="text-red-600">{JSON.stringify(error, null, 2)}</pre>}
      {profile && (
        <div className="mb-4">
          <div><strong>Email:</strong> {profile.email}</div>
          <div><strong>Nombre:</strong> {profile.full_name || '—'}</div>
        </div>
      )}

      {/* Removed inline save/edit form - Profile should only list saved chats */}

      <div>
        <h3 className="font-medium mb-2">Proyectos guardados</h3>
        <div className="mb-3">
          <button className="px-3 py-1 bg-red-600 text-white rounded" onClick={()=>{
            if(typeof logout === 'function'){
              logout()
            } else {
              localStorage.removeItem('tfg_token')
              // redirect to home
              window.location.href = '/'
            }
          }}>Cerrar sesión</button>
        </div>
        {chats.length === 0 && <div className="text-sm text-gray-500">No hay proyectos guardados.</div>}
        <div className="space-y-2">
          {chats.map(c => (
            <div key={c.id} className="border rounded p-2">
              <button className="text-left w-full" onClick={() => onOpenChat ? onOpenChat(c) : null}>
                <div className="font-medium">{c.title || `Proyecto ${c.id}`}</div>
                <div className="text-xs text-gray-500">{new Date(c.updated_at).toLocaleString()}</div>
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
