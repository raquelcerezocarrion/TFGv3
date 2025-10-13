// src/components/Employees.jsx
import React, { useEffect, useMemo, useState } from 'react'
import axios from 'axios'

/**
 * Empleados con fallback local:
 * - Usa /user/employees (GET/POST/PUT/DELETE) si existe.
 * - Si el backend devuelve 404 o falla, persiste en localStorage ("employees_cache").
 */

const CACHE_KEY = 'employees_cache_v1'

const uid = () => `tmp_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
const isNotFound = (e) => (e?.response?.status === 404) || /not\s*found/i.test(JSON.stringify(e?.response?.data || e?.message || ''))
const toTextError = (e) => {
  const raw = e?.response?.data ?? e?.message ?? e
  if (typeof raw === 'string') return raw
  try { return JSON.stringify(raw) } catch { return String(raw) }
}
const readCache = () => {
  try { return JSON.parse(localStorage.getItem(CACHE_KEY) || '[]') } catch { return [] }
}
const writeCache = (arr) => localStorage.setItem(CACHE_KEY, JSON.stringify(arr || []))

export default function Employees({ token }) {
  const apiBase = `http://${window.location.hostname}:8000`
  const headers = token ? { Authorization: `Bearer ${token}` } : {}

  const [list, setList] = useState([])
  const [q, setQ] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  // formulario de alta
  const [form, setForm] = useState({ name: '', role: '', skills: '', availability_pct: 100 })

  // edición inline
  const [editingId, setEditingId] = useState(null)
  const [editRow, setEditRow] = useState(null)

  useEffect(() => { load() }, [])

  async function load() {
    setLoading(true); setError('')
    try {
      const r = await axios.get(`${apiBase}/user/employees`, { headers })
      const data = Array.isArray(r.data) ? r.data : []
      setList(data)
      // sincroniza cache con servidor (por si había offline)
      writeCache(data)
    } catch (e) {
      // si no existe el endpoint o falla, tiramos de cache local
      const cached = readCache()
      setList(cached)
      if (!isNotFound(e)) setError(toTextError(e))
    } finally { setLoading(false) }
  }

  async function createEmployee() {
    if (!form.name.trim()) return setError('El nombre es obligatorio.')
    if (!form.role.trim()) return setError('El rol es obligatorio.')
    setError('')

    const payload = { ...form }
    try {
      const r = await axios.post(`${apiBase}/user/employees`, payload, {
        headers: { ...headers, 'Content-Type': 'application/json' }
      })
      const created = r.data?.id ? r.data : { ...payload, id: uid() }
      const next = [created, ...list]
      setList(next)
      writeCache(next)
      setForm({ name: '', role: '', skills: '', availability_pct: 100 })
    } catch (e) {
      // Fallback local si 404 o red caída
      if (isNotFound(e) || !e?.response) {
        const created = { ...payload, id: uid() }
        const next = [created, ...list]
        setList(next)
        writeCache(next)
        setForm({ name: '', role: '', skills: '', availability_pct: 100 })
      } else {
        setError(toTextError(e))
      }
    }
  }

  async function updateEmployee(id, data) {
    setError('')
    try {
      const r = await axios.put(`${apiBase}/user/employees/${id}`, data, {
        headers: { ...headers, 'Content-Type': 'application/json' }
      })
      const serverItem = r.data || data
      const next = list.map(x => x.id === id ? { ...x, ...serverItem } : x)
      setList(next); writeCache(next)
    } catch (e) {
      if (isNotFound(e) || !e?.response) {
        // actualiza offline
        const next = list.map(x => x.id === id ? { ...x, ...data } : x)
        setList(next); writeCache(next)
      } else {
        setError(toTextError(e))
      }
    }
  }

  async function deleteEmployee(id) {
    if (!confirm('¿Eliminar este empleado?')) return
    setError('')
    try {
      await axios.delete(`${apiBase}/user/employees/${id}`, { headers })
      const next = list.filter(x => x.id !== id)
      setList(next); writeCache(next)
    } catch (e) {
      if (isNotFound(e) || !e?.response) {
        const next = list.filter(x => x.id !== id)
        setList(next); writeCache(next)
      } else {
        setError(toTextError(e))
      }
    }
  }

  const filtered = useMemo(() => {
    const t = q.trim().toLowerCase()
    if (!t) return list
    return list.filter(e =>
      (e.name || '').toLowerCase().includes(t) ||
      (e.role || '').toLowerCase().includes(t) ||
      (Array.isArray(e.skills) ? e.skills.join(',') : (e.skills || '')).toLowerCase().includes(t)
    )
  }, [q, list])

  return (
    <div className="p-4 md:p-6">
      <div className="rounded-3xl bg-white/70 backdrop-blur border shadow-xl p-5 space-y-6">
        {/* Cabecera */}
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Empleados</h2>
          <div className="w-72">
            <input
              className="w-full border rounded-xl px-3 py-2 text-sm"
              placeholder="Buscar por nombre, rol o skill…"
              value={q}
              onChange={e => setQ(e.target.value)}
            />
          </div>
        </div>

        {/* Alta */}
        <div className="rounded-2xl border bg-white p-4 shadow-sm">
          <div className="text-sm font-medium mb-3">Registrar empleado</div>
     <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
       <input className="border rounded-xl px-3 py-2 min-w-0" placeholder="Nombre"
         value={form.name} onChange={e=>setForm(f=>({...f, name:e.target.value}))}/>
       <input className="border rounded-xl px-3 py-2 min-w-0" placeholder="Rol (Backend, QA, PM...)"
         value={form.role} onChange={e=>setForm(f=>({...f, role:e.target.value}))}/>
       <input className="border rounded-xl px-3 py-2 min-w-0" placeholder="Habilidades (csv: react,sql,...)"
         value={form.skills} onChange={e=>setForm(f=>({...f, skills:e.target.value}))}/>
       <input type="number" min={0} max={100} className="border rounded-xl px-3 py-2 w-full max-w-[120px]"
         placeholder="% disponibilidad" value={form.availability_pct}
         onChange={e=>setForm(f=>({...f, availability_pct: parseInt(e.target.value||'0')}))}/>
       <div className="flex items-center">
    <button className="w-full px-3 py-2 rounded-xl bg-emerald-600 text-white hover:opacity-90"
       onClick={createEmployee}>
      Añadir
    </button>
       </div>
     </div>
        </div>

        {/* Errores */}
        {error && (
          <div className="rounded-xl border border-red-200 bg-red-50 text-red-700 p-3 text-sm">
            {error}
          </div>
        )}

        {/* Listado */}
        <div className="rounded-2xl border bg-white p-4 shadow-sm">
          {loading && <div className="text-sm text-gray-500">Cargando…</div>}
          {!loading && filtered.length === 0 && (
            <div className="text-sm text-gray-500">No hay empleados registrados.</div>
          )}
          {!loading && filtered.length > 0 && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-h-[55vh] overflow-y-auto pr-1 custom-scroll">
              {filtered.map(emp => {
                const isEditing = editingId === emp.id
                const skillsText = Array.isArray(emp.skills) ? emp.skills.join(', ') : (emp.skills || '')
                return (
                  <div key={emp.id} className="border rounded-xl p-3 bg-white/60 hover:bg-gray-50 transition shadow-sm">
                    {!isEditing ? (
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex-1">
                              <div className="font-medium break-words">{emp.name}</div>
                              <div className="text-[12px] text-gray-600 truncate">
                                {emp.role} · {emp.availability_pct ?? 100}% disp.
                              </div>
                              {skillsText && <div className="mt-1 text-[12px] text-gray-500 break-words">Skills: {skillsText}</div>}
                        </div>
                        <div className="flex items-center gap-2">
                          <button className="px-2 py-1 text-xs rounded-lg border"
                                  onClick={() => { setEditingId(emp.id); setEditRow({ ...emp, skills: skillsText }) }}>
                            Editar
                          </button>
                          <button className="px-2 py-1 text-xs rounded-lg border text-red-600"
                                  onClick={() => deleteEmployee(emp.id)}>
                            Eliminar
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div className="space-y-2">
                        <div className="grid grid-cols-1 md:grid-cols-5 gap-2 items-end">
                          <input className="border rounded px-2 py-1 text-sm min-w-0" value={editRow.name}
                                 onChange={e=>setEditRow(r=>({...r, name:e.target.value}))}/>
                          <input className="border rounded px-2 py-1 text-sm min-w-0" value={editRow.role}
                                 onChange={e=>setEditRow(r=>({...r, role:e.target.value}))}/>
                          <input className="border rounded px-2 py-1 text-sm min-w-0" value={editRow.skills}
                                 onChange={e=>setEditRow(r=>({...r, skills:e.target.value}))}/>
                          <input type="number" min={0} max={100}
                                 className="border rounded px-2 py-1 text-sm w-full max-w-[120px]" value={editRow.availability_pct ?? 100}
                                 onChange={e=>setEditRow(r=>({...r, availability_pct: parseInt(e.target.value||'0')}))}/>
                          <div className="flex items-center justify-end gap-2 flex-wrap md:flex-nowrap">
                            <button className="px-2 py-1 text-xs rounded-lg border w-full md:w-auto"
                                    onClick={() => { setEditingId(null); setEditRow(null) }}>
                              Cancelar
                            </button>
                            <button className="px-2 py-1 text-xs rounded-lg bg-emerald-600 text-white w-full md:w-auto"
                                    onClick={async () => {
                                      await updateEmployee(emp.id, {
                                        name: editRow.name,
                                        role: editRow.role,
                                        skills: editRow.skills,
                                        availability_pct: editRow.availability_pct
                                      })
                                      setEditingId(null); setEditRow(null)
                                    }}>
                              Guardar
                            </button>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
