import React, { useEffect, useState, useMemo } from 'react'
import axios from 'axios'
import Chat from './Chat.jsx'

// Polished, modular Seguimiento component.
// - Maintains original endpoints and behavior
// - Adds improved layout, skeletons, accessibility and clearer empty states

export default function Seguimiento({ token, chats, onContinue }) {
  const [loading, setLoading] = useState(false)
  const [selectedChat, setSelectedChat] = useState(null)
  const [step, setStep] = useState(1) // 1: choose project, 2: choose phase, 3: phase view + chat
  const [sessionId, setSessionId] = useState(null)
  const [proposals, setProposals] = useState([])
  const [selectedProposal, setSelectedProposal] = useState(null)
  const [phases, setPhases] = useState([])
  const [selectedPhaseIdx, setSelectedPhaseIdx] = useState(null)
  const [run, setRun] = useState(null)
  const [runLoading, setRunLoading] = useState(false)
  const [error, setError] = useState(null)
  const [showProjectChat, setShowProjectChat] = useState(false)
  const [projectChatSession, setProjectChatSession] = useState(null)
  const [projectChatMessages, setProjectChatMessages] = useState(null)

  const base = useMemo(() => `http://${window.location.hostname}:8000`, [])

  // Helper: headers for authorized requests
  function authHeaders() {
    return token ? { Authorization: `Bearer ${token}` } : {}
  }

  async function openSessionForChat(chat) {
    if (!token) { window.alert('Debes iniciar sesión para usar seguimiento.'); return }
    setError(null)
    setLoading(true)
    try {
      const res = await axios.post(`${base}/user/chats/${chat.id}/continue`, {}, { headers: authHeaders() })
      const sid = res.data.session_id
      setSessionId(sid)
      setSelectedChat(chat)
      await fetchProposalsForSession(sid, chat.id)
    } catch (e) {
      console.error('open session', e)
      setError('No pude abrir la sesión para este proyecto.')
    } finally { setLoading(false) }
  }

  async function fetchProposalsDirectFromChat(chat) {
    setError(null)
    setLoading(true)
    try {
      const r = await axios.get(`${base}/projects/from_chat/${chat.id}`)
      setSelectedChat(chat)
      const data = r.data || []
      setProposals(data)
      setSelectedProposal(null)
      setPhases([])
      setSelectedPhaseIdx(null)
      return data
    } catch (e) {
      console.error('direct fetch from_chat', e)
      setError('No encontré propuestas relacionadas con este chat.')
      setProposals([])
      return []
    } finally { setLoading(false) }
  }

  async function fetchProposalsForSession(sid, chatId = null) {
    setError(null)
    setLoading(true)
    try {
      const res = await axios.get(`${base}/projects/list`, { params: { session_id: sid } })
      let data = res.data || []
      if ((!data || data.length === 0) && chatId) {
        try {
          const r2 = await axios.get(`${base}/projects/from_chat/${chatId}`)
          data = r2.data || []
        } catch (e2) {
          console.debug('fetch from_chat fallback failed', e2)
        }
      }
      setProposals(data)
      setSelectedProposal(null)
      setPhases([])
      setSelectedPhaseIdx(null)
      if (!data || data.length === 0) setError('No hay propuestas generadas para esta sesión.')
    } catch (e) {
      console.error('fetch proposals', e)
      setError('No se pudieron recuperar las propuestas.')
      setProposals([])
    } finally { setLoading(false) }
  }

  async function selectProposal(proposal) {
    setSelectedProposal(proposal)
    setError(null)
    try {
      const res = await axios.get(`${base}/projects/${proposal.id}/phases`)
      setPhases(res.data || [])
      setSelectedPhaseIdx(null)
      return res.data || []
    } catch (e) {
      console.error('get phases', e)
      setPhases([])
      setError('No se pudieron obtener las fases de la propuesta.')
      return []
    }
  }

  async function createRunForProposal() {
    if (!token) { window.alert('Debes iniciar sesión para iniciar seguimiento.'); return }
    if (!selectedProposal) { window.alert('Selecciona primero una propuesta.'); return }
    setRunLoading(true)
    setError(null)
    try {
      const res = await axios.post(`${base}/projects/${selectedProposal.id}/tracking`, { name: `Seguimiento propuesta ${selectedProposal.id}` }, { headers: { ...authHeaders(), 'Content-Type': 'application/json' } })
      const runId = res.data.run_id
      await fetchRun(runId)
    } catch (e) {
      console.error('create run', e)
      setError('No se pudo iniciar seguimiento.')
    } finally { setRunLoading(false) }
  }

  async function fetchRun(runId) {
    if (!token) return
    setRunLoading(true)
    setError(null)
    try {
      const res = await axios.get(`${base}/projects/tracking/${runId}`, { headers: authHeaders() })
      setRun(res.data)
    } catch (e) {
      console.error('fetch run', e)
      setError('No pude recuperar el seguimiento.')
    } finally { setRunLoading(false) }
  }

  async function toggleTask(runId, taskIdx, completed) {
    if (!token) { window.alert('Autentícate para marcar tareas.'); return }
    try {
      await axios.post(`${base}/projects/tracking/${runId}/tasks/${taskIdx}/toggle`, { completed }, { headers: { ...authHeaders(), 'Content-Type': 'application/json' } })
      await fetchRun(runId)
    } catch (e) {
      console.error('toggle task', e)
      setError('No pude actualizar la tarea.')
    }
  }

  function selectPhase(idx) {
    setSelectedPhaseIdx(idx)
  }

  // Small subcomponents for clarity
  async function handleSelectProject(chat) {
    setError(null)
    setLoading(true)
    try {
      setSelectedChat(chat)
      // fetch proposals related to this saved chat
      const data = await fetchProposalsDirectFromChat(chat)
      // auto-select first proposal if available and load its phases
      if (data && data.length > 0) {
        const first = data[0]
        await selectProposal(first)
        setSelectedProposal(first)
      }
      // advance to phase selection step
      setStep(2)
    } catch (e) {
      console.error('handleSelectProject', e)
      setError('No se pudo cargar el proyecto seleccionado.')
    } finally { setLoading(false) }
  }

  const ChatItem = ({ c }) => (
    <div
      className="p-3 border rounded-md flex items-center justify-between shadow-sm bg-white hover:shadow-md cursor-pointer"
      role="listitem"
      onClick={() => handleSelectProject(c)}
    >
      <div className="flex-1 pr-2">
        <div className="text-sm font-medium text-gray-800">{c.title || `Proyecto ${c.id}`}</div>
        <div className="text-xs text-gray-500">Guardado: {c.created_at ? new Date(c.created_at).toLocaleString() : ''}</div>
      </div>
        <div className="flex gap-2">
          <button
            aria-label={`Seleccionar proyecto ${c.id}`}
            className="px-3 py-1 border rounded text-sm hover:bg-gray-50"
            onClick={(e) => { e.stopPropagation(); handleSelectProject(c) }}
          >
            Seleccionar
          </button>
          <button
            aria-label={`Cargar propuestas ${c.id}`}
            className="px-3 py-1 border rounded text-sm bg-white hover:bg-gray-50"
            onClick={(e) => { e.stopPropagation(); fetchProposalsDirectFromChat(c) }}
          >
            Cargar propuestas
          </button>
        </div>
    </div>
  )

  const ProposalCard = ({ p }) => (
    <article className={`p-4 border rounded-md shadow-sm bg-white ${selectedProposal?.id === p.id ? 'ring-2 ring-emerald-200' : ''}`} aria-labelledby={`proposal-${p.id}`}>
      <div className="flex justify-between items-start">
        <div>
          <h3 id={`proposal-${p.id}`} className="font-semibold text-sm">Propuesta #{p.id}</h3>
          <div className="text-xs text-gray-500">Metodología: {p.methodology || '—'}</div>
          <p className="mt-2 text-xs text-gray-600 line-clamp-3">{p.requirements || '—'}</p>
        </div>
        <div className="ml-4 flex-shrink-0 flex flex-col gap-2">
          <button className="px-3 py-1 bg-blue-600 text-white rounded text-sm" onClick={() => selectProposal(p)}>Ver fases</button>
          <button className="px-3 py-1 bg-indigo-600 text-white rounded text-sm" onClick={() => openProposalChat(p)}>Abrir chat</button>
        </div>
      </div>
    </article>
  )

  async function openProposalChat(proposal) {
    setError(null)
    setLoading(true)
    try {
      const res = await axios.get(`${base}/projects/${proposal.id}/open_session`)
      const sid = res.data.session_id
      const assistant_summary = res.data.assistant_summary
      // Build initial messages for Chat component
      const msgs = []
      if (proposal.requirements) msgs.push({ role: 'user', content: proposal.requirements, ts: proposal.created_at || new Date().toISOString() })
      if (assistant_summary) msgs.push({ role: 'assistant', content: assistant_summary, ts: new Date().toISOString() })
      setProjectChatSession(sid)
      setProjectChatMessages(msgs)
      setShowProjectChat(true)
    } catch (e) {
      console.error('openProposalChat', e)
      setError('No pude abrir el chat de la propuesta.')
    } finally { setLoading(false) }
  }

  // New: open proposal chat scoped to a specific phase
  async function openProposalPhaseChat(proposal, phaseIdx) {
    setError(null)
    setLoading(true)
    try {
      const res = await axios.get(`${base}/projects/${proposal.id}/open_session`)
      const sid = res.data.session_id
      const assistant_summary = res.data.assistant_summary
      const msgs = []
      // include phase context as initial user message so assistant is scoped
      const phase = (phases && phases[phaseIdx]) || null
      if (phase) {
        const phaseText = `Contexto de la fase seleccionada:\nNombre: ${phase.name}\nDescripción: ${phase.description || ''}\nChecklist:\n${(phase.checklist || []).map((t, i) => `${i+1}. ${t}`).join('\n')}`
        msgs.push({ role: 'user', content: phaseText, ts: new Date().toISOString() })
      }
      if (assistant_summary) msgs.push({ role: 'assistant', content: assistant_summary, ts: new Date().toISOString() })
      setProjectChatSession(sid)
      setProjectChatMessages(msgs)
      // move to phase view + chat
      setSelectedPhaseIdx(phaseIdx)
      setStep(3)
    } catch (e) {
      console.error('openProposalPhaseChat', e)
      setError('No pude abrir el chat de la fase.')
    } finally { setLoading(false) }
  }

  const PhaseCard = ({ ph, idx }) => (
    <div className={`p-3 border rounded-md bg-white shadow-sm ${selectedPhaseIdx === idx ? 'ring-2 ring-emerald-200' : ''}`}>
      <div className="flex justify-between items-start">
        <div>
          <div className="font-medium">{ph.name}</div>
          <div className="text-xs text-gray-500">{ph.weeks ? `${ph.weeks} semanas` : ''}</div>
        </div>
        <div className="ml-2">
          <button className="px-2 py-1 border rounded text-sm" onClick={() => selectPhase(idx)}>Abrir</button>
        </div>
      </div>
      {selectedPhaseIdx === idx && (
        <div className="mt-3 text-sm">
          <div className="font-semibold">Checklist sugerida</div>
          <ul className="list-disc list-inside mt-2">
            {(ph.checklist || []).map((t, i) => <li key={i} className="py-0.5 text-sm">{t}</li>)}
          </ul>
          <div className="mt-3 flex gap-2">
            <button className="px-3 py-1 bg-emerald-600 text-white rounded" onClick={() => createRunForProposal()} disabled={runLoading}>{runLoading ? 'Iniciando…' : 'Iniciar seguimiento'}</button>
          </div>
        </div>
      )}
    </div>
  )

  const RunView = ({ run }) => (
    <div className="p-3 border rounded-md bg-white shadow-sm">
      <div className="font-semibold">{run.name || `Seguimiento #${run.id}`}</div>
      {run.started_at && <div className="text-xs text-gray-500">Iniciado: {new Date(run.started_at).toLocaleString()}</div>}
      <div className="mt-3">
        <div className="font-medium">Tareas</div>
        <ul className="mt-2 space-y-2">
          {(run.tasks || []).map((t, i) => (
            <li key={t.id || i} className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <input aria-label={`Marcar tarea ${t.text}`} type="checkbox" checked={!!t.completed} onChange={(e) => toggleTask(run.id, i, e.target.checked)} />
                <div className={`${t.completed ? 'line-through text-gray-500' : ''}`}>{t.text}</div>
              </div>
              <div className="text-xs text-gray-400">Fase {t.phase_idx + 1}</div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )

  return (
    <section className="p-6">
      <header className="mb-6">
        <h2 className="text-2xl font-semibold">Seguimiento de proyectos</h2>
        <p className="text-sm text-gray-500 mt-1">Abre un proyecto guardado y trabaja sobre la propuesta final: fases, checklist y seguimiento.</p>
      </header>

      <div className="">
        {/* Step 1: project selection - only show saved projects */}
        {step === 1 && (
          <div>
            <div className="mb-3 font-medium">Proyectos guardados</div>
            <div role="list" className="space-y-3 max-w-2xl">
              {(chats || []).map(c => <ChatItem key={c.id} c={c} />)}
              {(!chats || chats.length === 0) && <div className="text-sm text-gray-500">No hay proyectos guardados. Genera una propuesta desde la conversación y guárdala.</div>}
            </div>
          </div>
        )}

        {/* Step 2: project selected - show only project name and phase selection */}
        {step === 2 && selectedChat && (
          <div className="max-w-3xl">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <h3 className="text-xl font-semibold">{selectedChat.title || `Proyecto ${selectedChat.id}`}</h3>
                <div className="text-xs text-gray-500">Guardado: {selectedChat.created_at ? new Date(selectedChat.created_at).toLocaleString() : ''}</div>
              </div>
              <div className="flex items-center gap-2">
                <button className="px-3 py-1 border rounded text-sm" onClick={() => { setStep(1); setSelectedChat(null); setProposals([]); setSelectedProposal(null); setPhases([]); }}>Volver</button>
              </div>
            </div>

            <div className="mb-3 font-medium">Selecciona la fase para hacer seguimiento</div>
            <div className="space-y-3">
              {loading && <div className="text-sm text-gray-500">Cargando fases…</div>}
              {!loading && !selectedProposal && <div className="text-sm text-gray-500">No hay propuesta seleccionada. Puedes pulsar "Cargar propuestas" en la lista de proyectos para intentar recuperar una propuesta asociada.</div>}
              {!loading && selectedProposal && phases.length === 0 && <div className="text-sm text-gray-500">No se encontraron fases para la propuesta seleccionada.</div>}
              {!loading && phases.map((ph, idx) => (
                <div key={idx} className="p-3 border rounded-md bg-white shadow-sm flex items-center justify-between">
                  <div>
                    <div className="font-medium">{ph.name}</div>
                    <div className="text-xs text-gray-500">{ph.weeks ? `${ph.weeks} semanas` : ''}</div>
                  </div>
                  <div className="flex gap-2">
                    <button className="px-3 py-1 border rounded text-sm" onClick={() => openProposalPhaseChat(selectedProposal, idx)}>Abrir fase</button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Step 3: phase view + chat - show only selected phase info and chat */}
        {step === 3 && selectedProposal && selectedPhaseIdx !== null && (
          <div className="max-w-4xl">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <h3 className="text-xl font-semibold">{selectedProposal.id ? `Propuesta #${selectedProposal.id}` : selectedChat?.title}</h3>
                <div className="text-sm text-gray-500">Fase: {phases[selectedPhaseIdx]?.name}</div>
              </div>
              <div className="flex items-center gap-2">
                <button className="px-3 py-1 border rounded text-sm" onClick={() => { setStep(2); setProjectChatSession(null); setProjectChatMessages(null); }}>Volver a fases</button>
                <button className="px-3 py-1 border rounded text-sm" onClick={() => { setStep(1); setSelectedChat(null); setSelectedProposal(null); setPhases([]); setProjectChatSession(null); setProjectChatMessages(null); }}>Volver a proyectos</button>
              </div>
            </div>

            <div className="mb-4 p-4 border rounded bg-white shadow-sm">
              <div className="font-semibold">{phases[selectedPhaseIdx]?.name}</div>
              <div className="text-sm text-gray-700 mt-2">{phases[selectedPhaseIdx]?.description || 'Sin descripción.'}</div>
              <div className="mt-3">
                <div className="font-medium">Checklist</div>
                <ul className="list-disc list-inside mt-2">
                  {(phases[selectedPhaseIdx]?.checklist || []).map((t, i) => <li key={i} className="py-0.5 text-sm">{t}</li>)}
                </ul>
              </div>
            </div>

            <div className="p-0 bg-white rounded">
              <Chat token={token} loadedMessages={projectChatMessages} sessionId={projectChatSession} />
            </div>
          </div>
        )}
      </div>
      {/* Modal: chat for selected proposal */}
      {showProjectChat && (
        <div className="fixed inset-0 z-50 flex items-start justify-center pt-10">
          <div className="absolute inset-0 bg-black/40" onClick={() => setShowProjectChat(false)} />
          <div className="relative z-60 w-[95%] max-w-4xl bg-white rounded-2xl shadow-xl">
            <div className="flex items-center justify-between p-3 border-b">
              <div className="font-semibold">Chat de proyecto — Asistente en Seguimiento</div>
              <div className="flex items-center gap-2">
                <button className="px-3 py-1 border rounded" onClick={() => setShowProjectChat(false)}>Cerrar</button>
              </div>
            </div>
            <div className="p-3 h-[60vh]">
              <Chat token={token} loadedMessages={projectChatMessages} sessionId={projectChatSession} />
            </div>
          </div>
        </div>
      )}
    </section>
  )
}
