import React, { useMemo, useState } from 'react'

/**
 * Sidebar con búsqueda, nuevo chat y lista de chats guardados.
 * Añade el botón "Empleados".
 */
export default function Sidebar({
  chats = [],
  onSelect,
  onNew,
  onProfile,
  onEmployees,   // ← nuevo
  onRename,
  onDelete,
  onContinue
}) {
  const [q, setQ] = useState('')
  const [editingId, setEditingId] = useState(null)
  const [tempTitle, setTempTitle] = useState('')

  const filtered = useMemo(() => {
    const t = q.trim().toLowerCase()
    if (!t) return chats
    return chats.filter(c =>
      (c.title || '').toLowerCase().includes(t) ||
      (c.content || '').toLowerCase().includes(t)
    )
  }, [q, chats])

  const startEdit = (c) => { setEditingId(c.id); setTempTitle(c.title || '') }
  const commitEdit = async () => {
    if (!editingId) return
    try { await onRename?.(editingId, tempTitle || 'Sin título') } finally {
      setEditingId(null); setTempTitle('')
    }
  }

  return (
    <aside className="h-full flex flex-col gap-3">
      <div className="rounded-2xl p-3 bg-white/70 backdrop-blur border shadow-sm">
        <div className="flex items-center justify-between gap-2">
          <button
            className="px-3 py-2 rounded-xl bg-emerald-600 text-white hover:opacity-90 transition"
            onClick={() => onNew?.()}
          >
            Nuevo chat
          </button>
          <div className="flex items-center gap-2">
            <button
              className="px-3 py-2 rounded-xl border hover:bg-gray-50 transition"
              onClick={() => onEmployees?.()}   // ← aquí
              title="Empleados"
            >
              Empleados
            </button>
            <button
              className="px-3 py-2 rounded-xl border hover:bg-gray-50 transition"
              onClick={() => onProfile?.()}
              title="Perfil"
            >
              Perfil
            </button>
          </div>
        </div>

        <div className="mt-3">
          <input
            className="w-full rounded-xl border px-3 py-2 text-sm"
            placeholder="Buscar chats…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto pr-1 custom-scroll">
        {filtered.length === 0 && (
          <div className="text-xs text-gray-500 px-2">No hay resultados.</div>
        )}

        <ul className="space-y-2">
          {filtered.map((c) => {
            const isEditing = editingId === c.id
            return (
              <li key={c.id} className="group rounded-xl bg-white/70 backdrop-blur border shadow-sm">
                <div className="p-3">
                  <button className="text-left w-full" onClick={() => onSelect?.(c)}>
                    {!isEditing ? (
                      <>
                        <div className="font-medium line-clamp-1">{c.title || `Chat ${c.id}`}</div>
                        <div className="text-[11px] text-gray-500">{new Date(c.updated_at).toLocaleString()}</div>
                      </>
                    ) : (
                      <div className="flex items-center gap-2">
                        <input
                          autoFocus
                          className="flex-1 border rounded-lg px-2 py-1 text-sm"
                          value={tempTitle}
                          onChange={(e) => setTempTitle(e.target.value)}
                          onKeyDown={(e)=>{ if(e.key==='Enter') commitEdit(); if(e.key==='Escape'){ setEditingId(null); setTempTitle('') } }}
                        />
                        <button className="px-2 py-1 text-sm rounded-lg bg-emerald-600 text-white" onClick={commitEdit}>OK</button>
                        <button className="px-2 py-1 text-sm rounded-lg border" onClick={()=>{ setEditingId(null); setTempTitle('') }}>Cancelar</button>
                      </div>
                    )}
                  </button>

                  {!isEditing && (
                    <div className="mt-2 flex items-center gap-2 opacity-0 group-hover:opacity-100 transition">
                      <button className="px-2 py-1 text-xs rounded-lg border" onClick={() => onContinue?.(c)}>Cargar y continuar</button>
                      <button className="px-2 py-1 text-xs rounded-lg border" onClick={() => startEdit(c)}>Renombrar</button>
                      <button className="px-2 py-1 text-xs rounded-lg border text-red-600" onClick={() => onDelete?.(c.id)}>Eliminar</button>
                    </div>
                  )}
                </div>
              </li>
            )
          })}
        </ul>
      </div>
    </aside>
  )
}
