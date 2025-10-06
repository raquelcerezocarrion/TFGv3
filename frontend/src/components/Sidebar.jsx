import React from 'react'

export default function Sidebar({ chats, onSelect, onNew, onProfile, onRename, onDelete, onContinue }){
  return (
    <div className="h-full bg-gray-100 border-r p-3 flex flex-col">
      <div className="flex items-center justify-between mb-3">
        <button className="px-2 py-1 bg-emerald-600 text-white rounded" onClick={onNew}>Nuevo chat</button>
        <button className="px-2 py-1 border rounded" onClick={onProfile}>Perfil</button>
      </div>
      <div className="flex-1 overflow-y-auto">
        {chats && chats.length > 0 ? (
          chats.map(c => (
            <div key={c.id} className="p-2 rounded hover:bg-gray-200 cursor-pointer">
              <div onClick={()=>onSelect(c)}>
                <div className="font-medium">{c.title || `Chat ${c.id}`}</div>
                <div className="text-xs text-gray-500">{new Date(c.updated_at).toLocaleString()}</div>
              </div>
              <div className="mt-2 flex gap-2">
                <button className="px-2 py-1 border rounded" onClick={()=>onContinue && onContinue(c)}>Cargar y continuar</button>
                <button className="px-2 py-1 border rounded" onClick={()=>{ const t = prompt('Nuevo título', c.title || ''); if(t!==null) onRename && onRename(c.id, t) }}>Renombrar</button>
                <button className="px-2 py-1 border rounded text-red-600" onClick={()=>{ if(confirm('Eliminar chat?')) onDelete && onDelete(c.id) }}>Eliminar</button>
              </div>
            </div>
          ))
        ) : (
          <div className="text-sm text-gray-500">No hay chats guardados.</div>
        )}
      </div>
    </div>
  )
}
