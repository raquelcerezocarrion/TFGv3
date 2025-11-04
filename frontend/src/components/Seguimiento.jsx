import React, { useEffect, useState } from 'react'
import axios from 'axios'

export default function Seguimiento({ token, chats }) {
  const [loading, setLoading] = useState(false)
  const [selectedChat, setSelectedChat] = useState(null)
  const [sessionId, setSessionId] = useState(null)
  const [proposals, setProposals] = useState([])
  const [selectedProposal, setSelectedProposal] = useState(null)
  const [phases, setPhases] = useState([])
  const [selectedPhaseIdx, setSelectedPhaseIdx] = useState(null)
  const [run, setRun] = useState(null)
  const [runLoading, setRunLoading] = useState(false)

  const base = `http://${window.location.hostname}:8000`

  async function openSessionForChat(chat) {
    if (!token) { window.alert('Debes iniciar sesión para usar seguimiento.'); return }
    setLoading(true)
    try {
      const res = await axios.post(`${base}/user/chats/${chat.id}/continue`, {}, { headers: { Authorization: `Bearer ${token}` } })
      const sid = res.data.session_id
      setSessionId(sid)
      setSelectedChat(chat)
      await fetchProposalsForSession(sid)
    } catch (e) {
      console.error('open session', e)
      window.alert('No pude abrir la sesión para este proyecto.')
    } finally { setLoading(false) }
  }

  async function fetchProposalsForSession(sid) {
    try {
      const res = await axios.get(`${base}/projects/list`, { params: { session_id: sid } })
      setProposals(res.data || [])
      setSelectedProposal(null)
      setPhases([])
      setSelectedPhaseIdx(null)
    } catch (e) {
      console.error('fetch proposals', e)
      setProposals([])
    }
  }

  async function selectProposal(proposal) {
    setSelectedProposal(proposal)
    try {
      const res = await axios.get(`${base}/projects/${proposal.id}/phases`)
      setPhases(res.data || [])
      setSelectedPhaseIdx(null)
    } catch (e) {
      console.error('get phases', e)
      setPhases([])
    }
  }

  async function createRunForProposal() {
    if (!token) { window.alert('Debes iniciar sesión para iniciar seguimiento.'); return }
    if (!selectedProposal) { window.alert('Selecciona primero una propuesta.'); return }
    setRunLoading(true)
    try {
      const res = await axios.post(`${base}/projects/${selectedProposal.id}/tracking`, { name: `Seguimiento propuesta ${selectedProposal.id}` }, { headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' } })
      const runId = res.data.run_id
      await fetchRun(runId)
    } catch (e) {
      console.error('create run', e)
      window.alert('No se pudo iniciar seguimiento.')
    } finally { setRunLoading(false) }
  }

  async function fetchRun(runId) {
    if (!token) return
    setRunLoading(true)
    try {
      const res = await axios.get(`${base}/projects/tracking/${runId}`, { headers: { Authorization: `Bearer ${token}` } })
      setRun(res.data)
    } catch (e) {
      console.error('fetch run', e)
      window.alert('No pude recuperar el seguimiento.')
    } finally { setRunLoading(false) }
  }

  async function toggleTask(runId, taskIdx, completed) {
    if (!token) { window.alert('Autentícate para marcar tareas.'); return }
    try {
      const res = await axios.post(`${base}/projects/tracking/${runId}/tasks/${taskIdx}/toggle`, { completed }, { headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' } })
      // Refresh run to get updated tasks
      await fetchRun(runId)
    } catch (e) {
      console.error('toggle task', e)
      window.alert('No pude actualizar la tarea.')
    }
  }

  function selectPhase(idx) {
    setSelectedPhaseIdx(idx)
  }

  return (
    <div className="p-4">
      <h2 className="text-lg font-semibold mb-3">Seguimiento de proyectos</h2>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="col-span-1">
          <div className="mb-2 font-medium">Selecciona proyecto (guardado)</div>
          <div className="space-y-2">
            {(chats || []).map(c => (
              <div key={c.id} className="p-2 border rounded flex items-center justify-between">
                <div className="text-sm">{c.title || (`Proyecto ${c.id}`)}</div>
                <div className="flex gap-2">
                  <button className="px-2 py-1 text-sm border rounded" onClick={() => openSessionForChat(c)}>
                    Abrir seguimiento
                  </button>
                </div>
              </div>
            ))}
            {(!chats || chats.length === 0) && <div className="text-sm text-gray-500">No hay proyectos guardados. Crea uno desde Proyectos.</div>}
          </div>
        </div>

        <div className="col-span-1">
          <div className="mb-2 font-medium">Propuestas para la sesión</div>
          <div className="space-y-2">
            {loading && <div className="text-sm text-gray-500">Cargando…</div>}
            {!loading && sessionId && proposals.length === 0 && <div className="text-sm text-gray-500">No hay propuestas generadas para esta sesión.</div>}
            {proposals.map(p => (
              <div key={p.id} className={`p-2 border rounded ${selectedProposal && selectedProposal.id === p.id ? 'bg-emerald-50' : ''}`}>
                <div className="flex justify-between items-center">
                  <div>
                    <div className="font-medium">Propuesta #{p.id}</div>
                    <div className="text-xs text-gray-600">Metodología: {p.methodology || '—'}</div>
                    <div className="text-xs text-gray-500">{p.requirements?.slice(0,120)}</div>
                  </div>
                  <div>
                    <button className="px-2 py-1 rounded bg-blue-600 text-white text-sm" onClick={() => selectProposal(p)}>Ver fases</button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="col-span-1">
          <div className="mb-2 font-medium">Fases / Checklist</div>
          <div className="space-y-2">
            {!selectedProposal && <div className="text-sm text-gray-500">Selecciona una propuesta para ver fases.</div>}
            {phases.map((ph, idx) => (
              <div key={idx} className={`p-2 border rounded ${selectedPhaseIdx === idx ? 'bg-emerald-50' : ''}`}>
                <div className="flex items-center justify-between">
                  <div>
                    <div className="font-medium">{ph.name}</div>
                    <div className="text-xs text-gray-600">{ph.weeks ? `${ph.weeks} semanas` : ''}</div>
                  </div>
                  <div>
                    <button className="px-2 py-1 text-sm border rounded" onClick={() => selectPhase(idx)}>Abrir</button>
                  </div>
                </div>
                {selectedPhaseIdx === idx && (
                  <div className="mt-2 text-sm">
                    <div className="font-semibold">Checklist sugerida:</div>
                    <ul className="list-disc list-inside mt-1 text-sm">
                      {(ph.checklist || []).map((t, i) => (
                        <li key={i} className="py-0.5">{t}</li>
                      ))}
                    </ul>
                    <div className="mt-2 flex gap-2">
                      <button className="px-3 py-1 bg-emerald-600 text-white rounded" onClick={() => createRunForProposal()} disabled={runLoading}>{runLoading ? 'Iniciando…' : 'Iniciar seguimiento'}</button>
                      <button className="px-3 py-1 border rounded" onClick={() => alert('Puedes iniciar seguimiento y luego marcar tareas directamente.')}>Marcar tareas</button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
        <div className="col-span-1">
          <div className="mb-2 font-medium">Seguimiento activo</div>
          <div className="space-y-2">
            {!run && <div className="text-sm text-gray-500">No hay seguimiento activo. Inicia uno desde una fase.</div>}
            {run && (
              <div className="p-2 border rounded">
                <div className="font-medium">{run.name || `Seguimiento #${run.id}`}</div>
                <div className="text-xs text-gray-600">Iniciado: {new Date(run.started_at).toLocaleString()}</div>
                <div className="mt-2">
                  <div className="font-semibold">Tareas</div>
                  <ul className="mt-2 space-y-1 text-sm">
                    {(run.tasks || []).map((t, i) => (
                      <li key={t.id} className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <input type="checkbox" checked={t.completed} onChange={(e) => toggleTask(run.id, i, e.target.checked)} />
                          <div className={`${t.completed ? 'line-through text-gray-500' : ''}`}>{t.text}</div>
                        </div>
                        <div className="text-xs text-gray-400">Fase {t.phase_idx + 1}</div>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
