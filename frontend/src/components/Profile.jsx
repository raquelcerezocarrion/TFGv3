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
    <div className="h-full flex flex-col p-6">
      {/* Header con información del perfil */}
      <div className="bg-gradient-to-r from-blue-600 to-purple-600 rounded-2xl p-6 mb-6 text-white shadow-lg">
        <div className="flex items-center gap-4 mb-4">
          <div className="w-16 h-16 bg-white/20 rounded-full flex items-center justify-center text-3xl">
            👤
          </div>
          <div className="flex-1">
            <h2 className="text-2xl font-bold mb-1">Mi perfil</h2>
            {loading && <div className="text-sm text-white/80">Cargando...</div>}
          </div>
        </div>
        
        {profile && (
          <div className="space-y-2 bg-white/10 rounded-xl p-4 backdrop-blur">
            <div className="flex items-center gap-2">
              <span className="text-lg">📧</span>
              <div>
                <span className="text-xs text-white/70">Email:</span>
                <div className="font-medium">{profile.email}</div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-lg">🏷️</span>
              <div>
                <span className="text-xs text-white/70">Nombre:</span>
                <div className="font-medium">{profile.full_name || 'Sin nombre'}</div>
              </div>
            </div>
          </div>
        )}
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 mb-4">
          <div className="flex items-center gap-2 text-red-700">
            <span className="text-xl">⚠️</span>
            <pre className="text-sm">{JSON.stringify(error, null, 2)}</pre>
          </div>
        </div>
      )}

      {/* Proyectos guardados */}
      <div className="flex-1 overflow-hidden flex flex-col">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-xl font-bold text-gray-800 flex items-center gap-2">
            <span className="text-2xl">📁</span>
            Proyectos guardados
          </h3>
          <button 
            className="px-4 py-2 bg-red-600 text-white rounded-xl font-semibold hover:bg-red-700 transition shadow-md flex items-center gap-2"
            onClick={()=>{
              if(typeof logout === 'function'){
                logout()
              } else {
                localStorage.removeItem('tfg_token')
                window.location.href = '/'
              }
            }}
          >
            <span>🚪</span>
            Cerrar sesión
          </button>
        </div>

        <div className="flex-1 overflow-y-auto pr-2 custom-scroll">
          {chats.length === 0 ? (
            <div className="text-center py-12">
              <div className="text-6xl mb-4">📂</div>
              <p className="text-gray-500">No hay proyectos guardados aún</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {chats.map(c => (
                <button 
                  key={c.id} 
                  className="bg-white border-2 border-gray-200 rounded-xl p-4 hover:border-blue-400 hover:shadow-lg transition text-left group"
                  onClick={() => onOpenChat ? onOpenChat(c) : null}
                >
                  <div className="flex items-start gap-3">
                    <span className="text-2xl group-hover:scale-110 transition">📄</span>
                    <div className="flex-1 min-w-0">
                      <div className="font-semibold text-gray-800 truncate mb-1">
                        {c.title || `Proyecto ${c.id}`}
                      </div>
                      <div className="flex items-center gap-1 text-xs text-gray-500">
                        <span>🕒</span>
                        {new Date(c.updated_at).toLocaleString()}
                      </div>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
