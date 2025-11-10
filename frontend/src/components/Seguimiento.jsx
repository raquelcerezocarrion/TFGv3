import React, { useEffect, useState, useMemo } from 'react'
import axios from 'axios'
import Chat from './Chat.jsx'

// Polished, modular Seguimiento component.
// - Maintains original endpoints and behavior
// - Adds improved layout, skeletons, accessibility and clearer empty states

export default function Seguimiento({ token, chats, onContinue, onSaveCurrentChat, onSaveExistingChat }) {
  const [loading, setLoading] = useState(false)
  const [selectedChat, setSelectedChat] = useState(null)
  const [step, setStep] = useState(1) // 1: choose project, 2: choose proposal, 3: choose phase, 4: phase view + chat
  const [sessionId, setSessionId] = useState(null)
  const [proposals, setProposals] = useState([])
  const [selectedProposal, setSelectedProposal] = useState(null)
  const [phases, setPhases] = useState([])
  const [selectedPhaseIdx, setSelectedPhaseIdx] = useState(null)
  const [run, setRun] = useState(null)
  const [runLoading, setRunLoading] = useState(false)
  const [error, setError] = useState(null)
  const [showFollowUpChat, setShowFollowUpChat] = useState(false)
  const [projectChatSession, setProjectChatSession] = useState(null)
  const [projectChatMessages, setProjectChatMessages] = useState(null)
  const [followUpProposal, setFollowUpProposal] = useState(null)
  const [followUpView, setFollowUpView] = useState('actions') // 'actions' | 'chat'
  const [externalMessage, setExternalMessage] = useState(null)
  const [externalMessageId, setExternalMessageId] = useState(null)
  const [phaseDefLoading, setPhaseDefLoading] = useState(false)

  const base = useMemo(() => `http://${window.location.hostname}:8000`, [])

  // Helper to parse phases from assistant/proposal text when backend didn't return phases
  function parsePhasesFromText(text) {
    if (!text) return []
    const m = text.match(/Fases[:\s]+([^\n\r]+)/i)
    if (!m) return []
    const raw = m[1].trim()
    const parts = raw.split(/→|->|\+|,/) .map(s => s.trim()).filter(Boolean)
    return parts.map(p => {
      const wk = p.match(/\((\s*\d+)\s*[swd]?\)/i)
      const weeks = wk ? parseInt(wk[1].trim(), 10) : undefined
      const name = p.replace(/\([^)]*\)/g, '').trim()
      return { name, weeks, checklist: [] }
    })
  }

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
      // Ensure we only load proposals that were produced in this saved chat
      await fetchProposalsDirectFromChat(chat)
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
    // ALWAYS request structured definition from backend when opening a phase
    try {
      const ph = (phases && phases[idx]) || null
      if (ph && selectedProposal && selectedProposal.id) {
        ;(async () => {
          setPhaseDefLoading(true)
          try {
            const res = await axios.get(`${base}/projects/${selectedProposal.id}/phases/${idx}/definition`)
            console.log('🔍 Phase definition response:', res.data)
            const def = res.data && res.data.definition
            const structured = res.data && res.data.structured
            
            if (structured) {
              console.log('✅ Structured data received:', structured)
              // merge structured fields into phase
              setPhases(prev => {
                const copy = (prev || []).slice()
                const current = copy[idx] || {}
                copy[idx] = {
                  ...current,
                  description: def || structured.summary || current.description,
                  goals: structured.goals || structured.objectives || current.goals,
                  kpis: structured.kpis || current.kpis,
                  roles: structured.roles_responsibilities || current.roles,
                  deliverables: structured.deliverables || current.deliverables,
                  questions: structured.questions_to_ask || current.questions,
                  checklist: structured.checklist || current.checklist
                }
                console.log('📝 Updated phase data:', copy[idx])
                return copy
              })
            } else if (def) {
              console.log('⚠️ Only definition received, no structured data')
              setPhases(prev => {
                const copy = (prev || []).slice()
                copy[idx] = { ...(copy[idx] || {}), description: def }
                return copy
              })
            }
          } catch (e) {
            console.error('❌ Error fetching phase definition:', e)
          } finally {
            setPhaseDefLoading(false)
          }
        })()
      }
    } catch (e) {
      console.error('❌ Error in selectPhase:', e)
    }
  }

  // Small subcomponents for clarity
  async function handleSelectProject(chat) {
    setError(null)
    setLoading(true)
    try {
      setSelectedChat(chat)
      setStep(2)
    } catch (e) {
      console.error('handleSelectProject', e)
      setError('No se pudo cargar el proyecto seleccionado.')
    } finally { setLoading(false) }
  }

  const ChatItem = ({ c }) => (
    <div
      className="p-3 border rounded-md flex items-center justify-between shadow-sm bg-white"
      role="listitem"
    >
      <div className="flex-1 pr-2">
        <div className="text-sm font-medium text-gray-800">{c.title || `Proyecto ${c.id}`}</div>
        <div className="text-xs text-gray-500">Guardado: {c.created_at ? new Date(c.created_at).toLocaleString() : ''}</div>
      </div>
        <div className="flex gap-2">
          <button
            aria-label={`Cargar propuestas ${c.id}`}
            className="px-3 py-1 border rounded text-sm bg-white hover:bg-gray-50"
            onClick={() => {
              setSelectedChat(c);
              setStep(2);
              fetchProposalsDirectFromChat(c);
            }}
          >
            Cargar propuestas
          </button>
        </div>
    </div>
  )

  const ProposalCard = ({ p }) => (
    <article className={`p-4 border rounded-md shadow-sm bg-white ${selectedProposal?.id === p.id ? 'ring-2 ring-emerald-200' : ''}`} aria-labelledby={`proposal-${p.id || 'inline'}`}>
      <div className="flex justify-between items-start">
        <div>
          <h3 id={`proposal-${p.id || 'inline'}`} className="font-semibold text-sm">{p.id ? `Propuesta #${p.id}` : 'Propuesta (chat)'}</h3>
          <div className="text-xs text-gray-500">Metodología: {p.methodology || '—'}</div>
          <p className="mt-2 text-xs text-gray-600 line-clamp-3">{p.requirements || '—'}</p>
        </div>
        <div className="ml-4 flex-shrink-0 flex flex-col gap-2">
          {p.id ? (
            <>
              <button className="px-3 py-1 bg-blue-600 text-white rounded text-sm" onClick={async () => { await selectProposal(p); setSelectedProposal(p); setStep(3); }}>Ver fases</button>
              <button className="px-3 py-1 bg-indigo-600 text-white rounded text-sm" onClick={() => openProposalChat(p)}>Abrir chat</button>
            </>
          ) : (
            <>
              <button className="px-3 py-1 bg-emerald-600 text-white rounded text-sm" onClick={() => openProposalFollowUp(p)}>Empezar seguimiento</button>
              <button className="px-3 py-1 bg-indigo-600 text-white rounded text-sm" onClick={() => convertInlineProposal(p)}>Convertir en propuesta</button>
            </>
          )}
        </div>
      </div>
    </article>
  )

  // Open a chat seeded with an inline proposal (assistant message found in the saved chat)
  async function openProposalFollowUp(p) {
    setError(null)
    setLoading(true)
    try {
      // ensure we have a session for the saved chat
      if (!sessionId && selectedChat) {
        await openSessionForChat(selectedChat)
      }
      // Build messages: assistant content (the proposal) as assistant message
      const msgs = []
      if (p.requirements) msgs.push({ role: 'assistant', content: p.requirements, ts: p.created_at || new Date().toISOString() })
  setProjectChatSession(sessionId)
  setProjectChatMessages(msgs)
  setFollowUpView('actions')
  setFollowUpProposal(p)
  setShowFollowUpChat(true)
    } catch (e) {
      console.error('openProposalFollowUp', e)
      setError('No pude iniciar el seguimiento de la propuesta.')
    } finally { setLoading(false) }
  }

  async function convertInlineProposal(p) {
    if (!selectedChat) { setError('Selecciona primero un proyecto.'); return }
    setError(null)
    setLoading(true)
    try {
      const res = await axios.post(`${base}/projects/from_chat/${selectedChat.id}/to_proposal`, { content: p.requirements }, { headers: authHeaders() })
      const newId = res.data.proposal_id
      const created_at = res.data.created_at
      // Replace inline proposal in the list with the newly created ProposalLog entry
      const merged = (proposals || []).map(x => {
        if (x === p || (x.inline && x.requirements === p.requirements && x.created_at === p.created_at)) {
          return { id: newId, requirements: p.requirements, created_at: created_at, methodology: null }
        }
        return x
      })
      setProposals(merged)
      // Auto-select the new proposal and load its phases
      const newProposal = merged.find(x => x.id === newId)
      if (newProposal) {
        await selectProposal(newProposal)
        setSelectedProposal(newProposal)
        setStep(3)
      }
    } catch (e) {
      console.error('convertInlineProposal', e)
      setError('No pude convertir la propuesta.')
    } finally { setLoading(false) }
  }

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
    // Show phase info immediately so the user sees details while we open the session
    setError(null)
    const phase = (phases && phases[phaseIdx]) || null
    const initialMsgs = []
    if (phase) {
      // First message must be assistant greeting scoped to the selected phase
      initialMsgs.push({ role: 'assistant', content: `Hola! En qué te puedo ayudar sobre la fase ${phase.name}` , ts: new Date().toISOString() })
      // NOTE: We intentionally DO NOT push the full phase context as a 'user' message
      // because the UI previously showed it as a blue user bubble. The user requested
      // that only the assistant greeting remains visible. If later we need to send
      // the structured context to the backend without rendering it as a user bubble,
      // we can pass it via a hidden prop or include it in the proactive message.
    }
    // set UI to phase view immediately
    setProjectChatMessages(initialMsgs)
    setSelectedPhaseIdx(phaseIdx)
    setStep(4)

    // Request definition ALWAYS to get structured data (non-blocking; keep UI responsive)
    const ph = (phases && phases[phaseIdx]) || null
    if (ph && proposal && proposal.id) {
      try {
        setPhaseDefLoading(true)
        const r = await axios.get(`${base}/projects/${proposal.id}/phases/${phaseIdx}/definition`)
        console.log('🔍 Phase definition response (openProposalPhaseChat):', r.data)
        const d = r.data && r.data.definition
        const structured = r.data && r.data.structured
        
        if (structured) {
          console.log('✅ Structured data received (openProposalPhaseChat):', structured)
          setPhases(prev => {
            const copy = (prev || []).slice()
            const current = copy[phaseIdx] || {}
            copy[phaseIdx] = {
              ...current,
              description: d || structured.summary || current.description,
              goals: structured.goals || structured.objectives || current.goals,
              kpis: structured.kpis || current.kpis,
              roles: structured.roles_responsibilities || current.roles,
              deliverables: structured.deliverables || current.deliverables,
              questions: structured.questions_to_ask || current.questions,
              checklist: structured.checklist || current.checklist
            }
            console.log('📝 Updated phase data (openProposalPhaseChat):', copy[phaseIdx])
            return copy
          })
        } else if (d) {
          console.log('⚠️ Only definition received, no structured data (openProposalPhaseChat)')
          setPhases(prev => {
            const copy = (prev || []).slice()
            copy[phaseIdx] = { ...(copy[phaseIdx] || {}), description: d }
            return copy
          })
        }
      } catch (e) {
        console.error('❌ Error fetching phase definition (openProposalPhaseChat):', e)
      } finally {
        setPhaseDefLoading(false)
      }
    }

    // then open backend session asynchronously and append assistant summary when ready
    setLoading(true)
    try {
      const res = await axios.get(`${base}/projects/${proposal.id}/open_session`)
      const sid = res.data.session_id
      const assistant_summary = res.data.assistant_summary
      const msgs = [...initialMsgs]
      if (assistant_summary) msgs.push({ role: 'assistant', content: assistant_summary, ts: new Date().toISOString() })
      setProjectChatSession(sid)
      setProjectChatMessages(msgs)
      // Enviar proactivamente una petición al asistente (opción A)
      try {
        const proactive = `Proactividad: considerando la fase \"${phase?.name || ''}\" y la metodología ${proposal?.methodology || ''}, por favor propon 3 acciones prioritarias, 3 riesgos críticos a vigilar, una checklist mínima de 5 ítems y sugerencias de responsables para cada ítem.`
        setExternalMessage(proactive)
        setExternalMessageId(Date.now())
      } catch (e) {
        console.debug('No pude lanzar mensaje proactivo:', e)
      }
    } catch (e) {
      console.error('openProposalPhaseChat', e)
      // don't block the UI; show an inline error but keep phase view
      setError('No pude abrir el chat de la fase (el detalle de la fase sí está disponible).')
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
  <section className="p-6 bg-white rounded-2xl shadow-lg overflow-hidden box-border max-w-[1200px] mx-auto h-[calc(100vh-120px)]">
      <div className="hidden">
        <header className="mb-6">
          <h2 className="text-2xl font-semibold">Seguimiento de proyectos</h2>
          <p className="text-sm text-gray-500 mt-1">Abre un proyecto guardado y trabaja sobre la propuesta final: fases, checklist y seguimiento.</p>
        </header>
      </div>

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

        {/* Step 2: proposal selection (after choosing project). If exactly one proposal existed we skipped here. */}
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

            <div className="mb-3 font-medium">Propuestas encontradas</div>
            <div className="space-y-3">
              {loading && <div className="text-sm text-gray-500">Buscando propuestas…</div>}
              {!loading && (!proposals || proposals.length === 0) && <div className="text-sm text-gray-500">No se encontraron propuestas para este proyecto. Usa "Cargar propuestas" en la lista de proyectos o vuelve atrás.</div>}
              {!loading && proposals.map(p => (
                <ProposalCard key={p.id} p={p} />
              ))}
            </div>
          </div>
        )}

        {/* Step 3: phase selection - show phases for the chosen proposal */}
        {step === 3 && selectedProposal && (
          <div className="max-w-3xl">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <h3 className="text-xl font-semibold">{selectedProposal.id ? `Propuesta #${selectedProposal.id}` : selectedChat?.title}</h3>
                <div className="text-xs text-gray-500">Selecciona la fase para hacer seguimiento</div>
              </div>
              <div className="flex items-center gap-2">
                <button className="px-3 py-1 border rounded text-sm" onClick={() => { setStep(2); setSelectedProposal(null); setPhases([]); setProjectChatSession(null); setProjectChatMessages(null); }}>Volver a propuestas</button>
                <button className="px-3 py-1 border rounded text-sm" onClick={() => { setStep(1); setSelectedChat(null); setSelectedProposal(null); setPhases([]); setProjectChatSession(null); setProjectChatMessages(null); }}>Volver a proyectos</button>
              </div>
            </div>

            <div className="space-y-3">
              {loading && <div className="text-sm text-gray-500">Cargando fases…</div>}
              {!loading && phases.length === 0 && <div className="text-sm text-gray-500">No se encontraron fases para la propuesta seleccionada.</div>}
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

        {/* Step 4: phase view + chat - show only selected phase info and chat */}
        {step === 4 && selectedProposal && selectedPhaseIdx !== null && (
          <div className="w-full max-w-full mx-auto overflow-hidden box-border h-full flex flex-col">
            <div className="bg-white rounded-2xl p-4 overflow-hidden h-full flex flex-row gap-4">
              <div className="w-80 flex-shrink-0">
                <div className="p-4 bg-white border rounded-lg h-full flex flex-col justify-between">
                  <div>
                    <h3 className="text-lg font-semibold">{selectedProposal.id ? `Propuesta #${selectedProposal.id}` : selectedChat?.title}</h3>
                    <div className="text-xs text-gray-500 mt-1">Fase: <span className="font-medium">{phases[selectedPhaseIdx]?.name}</span></div>

                    <div className="mt-3 text-sm text-gray-700">
                      <div className="font-medium">Descripción</div>
                      <div className="mt-1 text-xs text-gray-600">{phases[selectedPhaseIdx]?.description || phases[selectedPhaseIdx]?.summary || 'Sin descripción disponible.'}</div>
                    </div>

                    <div className="mt-4">
                      <div className="font-medium text-sm">Checklist</div>
                      <ul className="list-disc list-inside mt-2 text-sm text-gray-700 space-y-1">
                        {(phases[selectedPhaseIdx]?.checklist || []).slice(0,8).map((t,i) => <li key={i}>{t}</li>)}
                        {(!phases[selectedPhaseIdx]?.checklist || phases[selectedPhaseIdx].checklist.length===0) && <li className="text-xs text-gray-500">No hay checklist disponible.</li>}
                      </ul>
                    </div>

                    <div className="mt-4">
                      <div className="font-medium text-sm">KPIs</div>
                      <ul className="list-disc list-inside mt-2 text-sm text-gray-700 space-y-1">
                        {(phases[selectedPhaseIdx]?.kpis || []).slice(0,6).map((k,i) => <li key={i}>{k}</li>)}
                        {(!phases[selectedPhaseIdx]?.kpis || phases[selectedPhaseIdx].kpis.length===0) && <li className="text-xs text-gray-500">No hay KPIs definidos.</li>}
                      </ul>
                    </div>
                  </div>

                  <div className="mt-4 flex flex-col gap-2">
                    <button className="px-3 py-1 border rounded text-sm" onClick={() => { setStep(3); setProjectChatSession(null); setProjectChatMessages(null); }}>Volver a fases</button>
                    <button className="px-3 py-1 border rounded text-sm" onClick={() => { setStep(1); setSelectedChat(null); setSelectedProposal(null); setPhases([]); setProjectChatSession(null); setProjectChatMessages(null); }}>Volver a proyectos</button>
                    <button className="px-3 py-1 bg-emerald-600 text-white rounded text-sm" onClick={() => createRunForProposal()} disabled={runLoading}>{runLoading ? 'Iniciando…' : 'Iniciar seguimiento'}</button>
                  </div>
                </div>
              </div>

              {/* Right: Chat panel, fixed-height so messages scroll internally */}
              <div className="flex-1 min-w-0 flex flex-col">
                <div className="h-[64vh] p-2 min-h-0">
                  <Chat 
                    token={token} 
                    loadedMessages={projectChatMessages} 
                    sessionId={projectChatSession} 
                    externalMessage={externalMessage} 
                    externalMessageId={externalMessageId} 
                    phase={phases[selectedPhaseIdx]?.name || null}
                    onSaveCurrentChat={onSaveCurrentChat}
                    onSaveExistingChat={onSaveExistingChat}
                    selectedChatId={selectedChat?.id || null}
                  />
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
      {/* Nueva vista dedicada para seguimiento */}
      {showFollowUpChat && (
        <div className="fixed inset-0 z-50 flex flex-col bg-white">
          <div className="flex items-center justify-between p-4 border-b">
            <div>
              <h2 className="text-xl font-semibold">Seguimiento del proyecto</h2>
              {followUpProposal && (
                <div className="text-sm text-gray-600 mt-1">
                  Metodología: {followUpProposal.methodology || '—'}
                </div>
              )}
            </div>
            <div className="flex items-center gap-2">
              <button
                className={`px-3 py-1 rounded text-sm ${followUpView === 'actions' ? 'bg-emerald-600 text-white' : 'border'}`}
                onClick={() => setFollowUpView('actions')}
              >
                Acciones sugeridas
              </button>

              <button
                className={`px-3 py-1 rounded text-sm border`}
                onClick={async () => {
                  if (!followUpProposal) return
                  // ensure we have phases loaded for the proposal; try backend first, then parse from assistant text
                  setSelectedProposal(followUpProposal)
                  if (!phases || phases.length === 0) {
                    // try to fetch from backend if proposal has id
                    if (followUpProposal.id) {
                      try {
                        const res = await axios.get(`${base}/projects/${followUpProposal.id}/phases`)
                        setPhases(res.data || [])
                      } catch (e) {
                        // ignore
                      }
                    }
                    // still empty? try parse from assistant/proposal text
                    if ((!phases || phases.length === 0) && followUpProposal.requirements) {
                      const parsed = parsePhasesFromText(followUpProposal.requirements)
                      if (parsed && parsed.length > 0) setPhases(parsed)
                    }
                    // fallback: if we have projectChatMessages (assistant content), try parse
                    if ((!phases || phases.length === 0) && projectChatMessages && projectChatMessages.length > 0) {
                      const parsed2 = parsePhasesFromText(projectChatMessages[0].content)
                      if (parsed2 && parsed2.length > 0) setPhases(parsed2)
                    }
                  }
                  setShowFollowUpChat(false)
                  setStep(3)
                }}
              >
                Ver fases
              </button>

              <button 
                className="px-3 py-1 border rounded text-sm" 
                onClick={() => {
                  setShowFollowUpChat(false);
                  setFollowUpProposal(null);
                  setProjectChatSession(null);
                  setProjectChatMessages(null);
                }}
              >
                Volver a propuestas
              </button>
            </div>
          </div>
          <div className="flex-1 p-4 overflow-auto">
            {/* Conditionally show suggested actions or the chat */}
            {followUpView === 'actions' && (
              <div className="mb-4">
                <h3 className="text-sm font-medium text-gray-700 mb-2">Acciones sugeridas:</h3>
                <div className="grid grid-cols-2 gap-2 md:grid-cols-3">
                  <button 
                    className="p-3 text-left border rounded-lg hover:bg-gray-50 flex items-center gap-2"
                    onClick={() => {
                      const msg = `Basándote en la metodología ${followUpProposal?.methodology || 'propuesta'} y el equipo definido, ¿podrías desglosar en detalle las tareas específicas de la fase inicial de Discovery y CRC? Necesito entender:\n1. Qué historias de usuario deberíamos priorizar\n2. Qué workshops o sesiones de refinamiento necesitamos\n3. Qué documentación técnica debemos preparar`;
                      setExternalMessage(msg)
                      setExternalMessageId(Date.now())
                      setFollowUpView('chat')
                    }}
                  >
                    <span className="text-blue-600">📋</span>
                    <span>Desglosar tareas de Discovery</span>
                  </button>

                  <button 
                    className="p-3 text-left border rounded-lg hover:bg-gray-50 flex items-center gap-2"
                    onClick={() => {
                      const msg = `Considerando el stack tecnológico del equipo (${followUpProposal?.requirements?.includes('Tech Stack') ? 'definido' : 'por definir'}) y los riesgos ya identificados:\n1. ¿Qué riesgos técnicos adicionales deberíamos considerar?\n2. ¿Qué medidas de mitigación sugieres para cada uno?\n3. ¿Cómo podríamos priorizar estos riesgos?`;
                      setExternalMessage(msg)
                      setExternalMessageId(Date.now())
                      setFollowUpView('chat')
                    }}
                  >
                    <span className="text-yellow-600">⚠️</span>
                    <span>Analizar riesgos técnicos</span>
                  </button>

                  <button 
                    className="p-3 text-left border rounded-lg hover:bg-gray-50 flex items-center gap-2"
                    onClick={() => {
                      const msg = `Para asegurar el éxito del proyecto y basándonos en el presupuesto de ${followUpProposal?.requirements?.match(/Presupuesto: ([^€]+)€/)?.[1] || 'asignado'} €:\n1. ¿Qué KPIs técnicos deberíamos monitorizar?\n2. ¿Qué métricas de calidad del código sugieres?\n3. ¿Cómo medimos el rendimiento del equipo?\n4. ¿Qué objetivos de negocio deberíamos trackear?`;
                      setExternalMessage(msg)
                      setExternalMessageId(Date.now())
                      setFollowUpView('chat')
                    }}
                  >
                    <span className="text-green-600">📊</span>
                    <span>Definir KPIs del proyecto</span>
                  </button>

                  <button 
                    className="p-3 text-left border rounded-lg hover:bg-gray-50 flex items-center gap-2"
                    onClick={() => {
                      const msg = `Para la fase de Hardening & Pruebas de Aceptación:\n1. ¿Qué estrategia de testing recomiendas para este proyecto?\n2. ¿Qué tipos de pruebas deberíamos incluir?\n3. ¿Cómo organizamos los test sprints?\n4. ¿Qué herramientas de testing sugieres para el stack técnico propuesto?`;
                      setExternalMessage(msg)
                      setExternalMessageId(Date.now())
                      setFollowUpView('chat')
                    }}
                  >
                    <span className="text-purple-600">🎯</span>
                    <span>Plan de pruebas y QA</span>
                  </button>

                  <button 
                    className="p-3 text-left border rounded-lg hover:bg-gray-50 flex items-center gap-2"
                    onClick={() => {
                      const msg = `Para la fase final de Release & Handover:\n1. ¿Qué estrategia de CI/CD recomiendas?\n2. ¿Cómo gestionamos los diferentes entornos?\n3. ¿Qué proceso de release sugieres?\n4. ¿Qué medidas de rollback y contingencia necesitamos?`;
                      setExternalMessage(msg)
                      setExternalMessageId(Date.now())
                      setFollowUpView('chat')
                    }}
                  >
                    <span className="text-indigo-600">🚀</span>
                    <span>Estrategia de despliegue</span>
                  </button>

                  <button 
                    className="p-3 text-left border rounded-lg hover:bg-gray-50 flex items-center gap-2"
                    onClick={() => {
                      const msg = `Para cada una de las fases del proyecto (${followUpProposal?.requirements?.match(/Fases: ([^→]+)/)?.[1] || 'definidas'}):\n1. ¿Qué entregables técnicos debemos generar?\n2. ¿Qué documentación es necesaria?\n3. ¿Qué criterios de aceptación sugieres para cada entregable?\n4. ¿Cómo validamos la calidad de cada entregable?`;
                      setExternalMessage(msg)
                      setExternalMessageId(Date.now())
                      setFollowUpView('chat')
                    }}
                  >
                    <span className="text-orange-600">📦</span>
                    <span>Definir entregables</span>
                  </button>
                </div>
              </div>
            )}

              {followUpView === 'chat' && (
              <div>
                <Chat token={token} loadedMessages={projectChatMessages} sessionId={projectChatSession} externalMessage={externalMessage} externalMessageId={externalMessageId} phase={phases[selectedPhaseIdx]?.name || null} onSaveCurrentChat={onSaveCurrentChat} onSaveExistingChat={onSaveExistingChat} selectedChatId={selectedChat?.id || null} />
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  )
}
