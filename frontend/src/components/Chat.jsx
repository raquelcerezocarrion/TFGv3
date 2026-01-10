import React, { useEffect, useRef, useState } from 'react'
import axios from 'axios'

const CANDIDATES = [
  () => `http://${window.location.hostname}:8000`,
  () => 'http://127.0.0.1:8000',
  () => 'http://localhost:8000',
]

async function detectApiBase() {
  for (const make of CANDIDATES) {
    const base = make()
    try { await axios.get(`${base}/health`, { timeout: 1500 }); return base } catch {}
  }
  return null
}

export default function Chat({ token, loadedMessages = null, selectedChatId = null, onSaveCurrentChat = null, onSaveExistingChat = null, sessionId: externalSessionId = null, externalMessage = null, externalMessageId = null, phase = null }) {
  const [apiBase, setApiBase] = useState(null)
  const [sessionId, setSessionId] = useState(() => 'demo-' + Math.random().toString(36).slice(2, 8))
  // Start empty; if parent doesn't provide `loadedMessages` we'll show a friendly greeting.
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const wsRef = useRef(null)
  const listRef = useRef(null)
  const messagesRef = useRef([])
  const [userHasScrolled, setUserHasScrolled] = useState(false)

  // Scroll to bottom, but only if the user hasn't scrolled up
  useEffect(() => {
    if (listRef.current && !userHasScrolled) {
      listRef.current.scrollTop = listRef.current.scrollHeight
    }
  }, [messages, userHasScrolled])

  // keep a ref copy of messages for async helpers to read the latest value
  useEffect(() => { messagesRef.current = messages }, [messages])

  // Detect assistant prompts and show CTA buttons
  // Helper: detect CTAs inside a given assistant text
  const detectCtas = (raw) => {
    try {
      if (!raw) return []
      const txt = String(raw).toLowerCase()
      
      // Don't detect CTAs in the initial welcome message
      if (txt.includes('hola, soy el asistente de propuestas') && txt.includes('recomendaciones de uso importantes')) {
        return []
      }
      
      const ctas = []
      if (txt.includes('acept') || txt.includes('acepto la propuesta') || txt.includes('aceptar la propuesta')) {
        ctas.push({ type: 'accept', label: 'Aceptar propuesta' })
      }
      // Employee-related options
      if (txt.includes('usar empleados') || txt.includes('cargar empleados') || (txt.includes('empleados') && txt.includes('guardad')) || txt.includes('usar empleados guardados')) {
        ctas.push({ type: 'load_employees', label: 'Cargar empleados' })
      }
      if (txt.includes('manual') || txt.includes('introducir plantilla') || txt.includes('introducir plantilla manualmente') || txt.includes('plantilla manual')) {
        ctas.push({ type: 'manual', label: 'Introducir plantilla' })
      }
      // Avoid offering the 'Iniciar proyecto' CTA for some long proposal messages
      const noStartPhrases = [
        'quieres comenzar el proyecto ahora',
        'quieres iniciar el proyecto ahora',
        'quieres empezar el proyecto ahora'
      ]
      const suppressStart = noStartPhrases.some(p => txt.includes(p))
      if (!suppressStart && (txt.includes('quieres comenzar') || txt.includes('quieres iniciar') || txt.includes('comenzamos') || txt.includes('empezamos')) && txt.includes('proyecto')) {
        ctas.push({ type: 'start', label: 'Iniciar proyecto' })
      }
      if (txt.includes('hacer cambios') || txt.includes('modific') || txt.includes('realizar cambios') || txt.includes('quieres que lo modifi')) {
        ctas.push({ type: 'changes', label: 'Solicitar cambios' })
      }
      return ctas
    } catch {
      return []
    }
  }

  // Detect if user scrolls up
  const handleScroll = () => {
    const { scrollTop, scrollHeight, clientHeight } = listRef.current
    // If user is not at the bottom, set the flag
    if (scrollTop + clientHeight < scrollHeight - 20) { // 20px buffer
      setUserHasScrolled(true)
    } else {
      setUserHasScrolled(false)
    }
  }
  const [showSaveDialog, setShowSaveDialog] = useState(false)
  const [saveTitle, setSaveTitle] = useState('')

  // export dialog
  const [showExport, setShowExport] = useState(false)
  const [loadingExport, setLoadingExport] = useState(false)
  const [title, setTitle] = useState('Informe de la conversación')
  const [reportMeta, setReportMeta] = useState({ project:'', client:'', author:'', session_id:'', subtitle:'Chat + decisiones + propuesta final' })
  const [reportOptions, setReportOptions] = useState({ include_cover:true, include_transcript:true, include_analysis:true, include_final_proposal:true, analysis_depth:'deep', font_name:'Helvetica' })

  // CTA buttons suggested by assistant (e.g., aceptar propuesta, pedir cambios, iniciar proyecto)
  const [suggestedCtas, setSuggestedCtas] = useState([])
  // Phase buttons shown when user confirms start; each item: { name, definition }
  const [phaseButtons, setPhaseButtons] = useState([])

  // descubrir backend + abrir WS
  useEffect(() => {
    (async () => {
      const base = await detectApiBase()
      if (!base) {
        setMessages(prev => [...prev, { role: 'assistant', content: '⚠️ No encuentro el backend en :8000. Arranca uvicorn.', ts: new Date().toISOString() }])
        return
      }
      setApiBase(base)

      try {
        const u = new URL(base)
        const proto = u.protocol === 'https:' ? 'wss' : 'ws'
        const wsUrl = `${proto}://${u.host}/chat/ws?session_id=${sessionId}`
        const ws = new WebSocket(wsUrl)
        wsRef.current = ws
        ws.onmessage = async (evt) => {
          const content = evt.data
          
          // Check if we already have a complete proposal message
          // If so, ignore any subsequent messages from the backend
          const hasCompleteProposal = messagesRef.current.some(m => 
            m.role === 'assistant' && 
            typeof m.content === 'string' && 
            m.content.includes('✅ He cargado') && 
            m.content.includes('empleados de tu base de datos') &&
            m.content.includes('Asignación por rol') &&
            m.content.includes('¿Quieres comenzar el proyecto ahora?')
          )
          
          if (hasCompleteProposal) {
            // Don't show any more messages after the complete proposal
            return
          }
          
          // 🔥 Auto-detectar si el backend pide JSON de empleados y cargarlos automáticamente
          const normalized = content.toLowerCase()
          const isAskingForEmployees = normalized.includes('envíame la lista de empleados') || 
              normalized.includes('enviame la lista de empleados') ||
              normalized.includes('envíame json') ||
              (normalized.includes('empleados') && normalized.includes('json'))
          
          // Don't show the message asking for employees JSON - just send it silently
          if (!isAskingForEmployees) {
            setMessages(prev => [...prev, { role: 'assistant', content, ts: new Date().toISOString() }])
          }
          
          // If backend is asking for employees, load and send them automatically
          if (isAskingForEmployees) {
            
            // Cargar empleados de la API
            try {
              const headers = token ? { Authorization: `Bearer ${token}` } : {}
              const { data } = await axios.get(`${base}/user/employees`, { headers })
              
              if (Array.isArray(data) && data.length > 0) {
                // Convertir al formato esperado por el backend
                const employeesJson = data.map(emp => ({
                  name: emp.name,
                  role: emp.role,
                  skills: emp.skills,
                  seniority: emp.seniority || 'Mid',
                  availability_pct: emp.availability_pct || 100
                }))
                
                // Enviar automáticamente el JSON sin mostrar mensajes intermedios
                const jsonString = JSON.stringify(employeesJson, null, 2)
                
                // Enviar el JSON directamente sin delays ni mensajes intermedios
                setTimeout(() => {
                  if (ws.readyState === WebSocket.OPEN) {
                    ws.send(jsonString)
                  }
                }, 200)
              } else {
                // No hay empleados guardados
                setTimeout(() => {
                  setMessages(prev => [...prev, { 
                    role: 'assistant', 
                    content: '⚠️ No tienes empleados guardados en la sección "Empleados". Puedes introducir la plantilla manualmente escribiendo "manual".', 
                    ts: new Date().toISOString() 
                  }])
                }, 500)
              }
            } catch (error) {
              console.error('Error cargando empleados:', error)
              // Silencioso - el usuario puede escribir "manual" si quiere
            }
          }

          // (Eliminada la navegación automática a Seguimiento)
        }
        ws.onerror = () =>
          setMessages(prev => [...prev, { role: 'assistant', content: '⚠️ No se pudo conectar por WebSocket. Usaré HTTP.', ts: new Date().toISOString() }])
      } catch {
        setMessages(prev => [...prev, { role: 'assistant', content: '⚠️ No se pudo conectar por WebSocket. Usaré HTTP.', ts: new Date().toISOString() }])
      }
    })()
  }, [sessionId])

  useEffect(()=>{ if(externalSessionId){ setSessionId(externalSessionId) } }, [externalSessionId])
  
  // Cuando `loadedMessages` es un array (incluso vacío) debemos respetarlo.
  // Antes se ignoraba el array vacío y se mostraba el mensaje inicial del asistente.
  useEffect(() => {
    if (!Array.isArray(loadedMessages)) return
    let mapped = (loadedMessages || []).map(m => ({ role: m.role, content: m.content, ts: m.ts || new Date().toISOString() }))
    
    // Truncate messages after the complete proposal message (if found)
    // This prevents showing follow-up messages after the final proposal
    const completeProposalIndex = mapped.findIndex(m => 
      m.role === 'assistant' && 
      typeof m.content === 'string' && 
      m.content.includes('✅ He cargado') && 
      m.content.includes('empleados de tu base de datos') &&
      m.content.includes('Asignación por rol') &&
      m.content.includes('¿Quieres comenzar el proyecto ahora?')
    )
    
    if (completeProposalIndex !== -1) {
      // Keep messages up to and including the complete proposal, discard everything after
      mapped = mapped.slice(0, completeProposalIndex + 1)
    }
    
    setMessages(mapped)
    setUserHasScrolled(false) // Reset scroll lock on new messages
  }, [loadedMessages])

  // If parent didn't pass `loadedMessages` or passed an empty array, show the default assistant greeting once.
  useEffect(() => {
    // Si loadedMessages es un array con mensajes, no mostrar el greeting
    if (Array.isArray(loadedMessages) && loadedMessages.length > 0) return
    if (messages.length > 0) return
    setMessages([{ role: 'assistant', content: '👋 Hola, soy el asistente de propuestas. Puedes escribir "aprender" para entrar en modo formación y aprender sobre metodologías, o directamente escribe tu propuesta (por ejemplo: /propuesta: requisitos del cliente).\n\n📋 Recomendaciones de uso importantes:\nLa plataforma ha sido diseñada para ser muy intuitiva. ✨ Simplemente siga las indicaciones y pulse los botones que aparecerán en cada paso para avanzar de forma guiada en la configuración de su proyecto.\n\n⚠️ Es importante que utilice los botones de "Aceptar" ✅ o "Terminar" ✅ cuando aparezcan, ya que estos le permitirán avanzar correctamente a las siguientes fases del proceso.', ts: new Date().toISOString() }])
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadedMessages])

  const send = async (overrideText = null) => {
    const text = (overrideText !== null ? String(overrideText) : input).trim()
    if (!text) return
    setMessages(prev => [...prev, { role: 'user', content: text, ts: new Date().toISOString() }])
    setInput('')
    setUserHasScrolled(false) // Auto-scroll to new message

    // 🧭 (Auto-guardar tras confirmación) — navegación a Seguimiento eliminada
    try {
      const t = text.toLowerCase()
      const isAffirmative = ['si', 'sí', 'vale', 'ok', 'vamos', 'empezar', 'empecemos'].some(k => t === k || t.startsWith(k))
      const lastAssistant = [...messages].reverse().find(m => m.role === 'assistant')
      const askedToStart = lastAssistant && lastAssistant.content && lastAssistant.content.toLowerCase().includes('quieres comenzar el proyecto')
      if (isAffirmative && askedToStart) {
        // User confirmed starting the project: show Phase 1 with employees/roles inside the chat.
        try {
          // Find assistant message that contains the proposal phases
          const assistantMsg = [...messages].reverse().find(m => m.role === 'assistant' && /fases?:/i.test(m.content || ''))
          const phases = assistantMsg ? extractPhasesFromText(assistantMsg.content) : []
          const phaseName = phases && phases.length > 0 ? phases[0] : null

          if (!phaseName) {
            setMessages(prev => [...prev, { role: 'assistant', content: 'He iniciado el proyecto, pero no he encontrado las fases en la propuesta para mostrar la Fase 1.', ts: new Date().toISOString() }])
            return
          }

          // Try to fetch saved employees from backend; if not available, ask user to provide them
          if (!apiBase) {
            setMessages(prev => [...prev, { role: 'assistant', content: `Fase 1: ${phaseName}\nNo se ha detectado el backend. Si tienes empleados guardados, por favor utiliza el botón 'Cargar empleados' o pégalos manualmente.`, ts: new Date().toISOString() }])
            return
          }

          const headers = token ? { Authorization: `Bearer ${token}` } : {}
          const { data } = await axios.get(`${apiBase}/user/employees`, { headers })
          if (!Array.isArray(data) || data.length === 0) {
            setMessages(prev => [...prev, { role: 'assistant', content: `Fase 1: ${phaseName}\nNo hay empleados guardados. Pulsa 'Cargar empleados' o pega la plantilla manualmente.`, ts: new Date().toISOString() }])
            return
          }

          // Group employees by role
          const groups = {}
          data.forEach(emp => {
            const roleKey = emp.role || 'Sin rol'
            if (!groups[roleKey]) groups[roleKey] = []
            groups[roleKey].push(emp.name || `${emp.first_name || ''} ${emp.last_name || ''}`.trim() || 'Empleado desconocido')
          })

          const lines = []
          lines.push(`Fase 1: ${phaseName}`)
          lines.push('Asignación de personal por rol:')
          Object.keys(groups).forEach(r => {
            lines.push(`• ${r}: ${groups[r].join(', ')}`)
          })

          const content = lines.join('\n')
          setMessages(prev => [...prev, { role: 'assistant', content, ts: new Date().toISOString() }])

          // Save chat including this assistant message
          const updated = [...messages, { role: 'user', content: text, ts: new Date().toISOString() }, { role: 'assistant', content, ts: new Date().toISOString() }]
          await saveChatIfNeeded(updated)
        } catch (e) {
          console.error('Error mostrando Fase 1 con empleados:', e)
          setMessages(prev => [...prev, { role: 'assistant', content: 'Error mostrando la Fase 1. Comprueba el backend o proporciona los empleados manualmente.', ts: new Date().toISOString() }])
        }
      }
    } catch {}

    if (!apiBase) {
      setMessages(prev => [...prev, { role: 'assistant', content: '⚠️ Backend no detectado.', ts: new Date().toISOString() }])
      return
    }

    // comando /propuesta
    if (text.toLowerCase().startsWith('/propuesta:')) {
      const req = text.split(':').slice(1).join(':').trim() || 'Proyecto genérico'
      try {
        const { data } = await axios.post(`${apiBase}/projects/proposal`, {
          session_id: sessionId, requirements: req
        }, { headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) }, timeout: 5000 })

        const pretty = [
          `■ Metodología: ${data.methodology}`,
          `■ Equipo: ${data.team.map(t => `${t.role} x${t.count}`).join(', ')}`,
          `■ Fases: ${data.phases.map(p => `${p.name} (${p.weeks} semanas)`).join(' → ')}`,
          `■ Presupuesto: ${data.budget.total_eur} € (incluye ${data.budget.contingency_pct}% contingencia)`,
          `■■ Riesgos: ${data.risks.join('; ')}`,
          `Semanas totales: ${data.phases.reduce((a,b)=>a+b.weeks,0)}`
        ].join('\n')

        setMessages(prev => [...prev, { role: 'assistant', content: pretty, ts: new Date().toISOString() }])
      } catch (e) {
        const msg = e?.response?.data?.detail || e?.message || 'Error obteniendo la propuesta.'
        setMessages(prev => [...prev, { role: 'assistant', content: `⚠️ ${msg}`, ts: new Date().toISOString() }])
      }
      return
    }

    // WS si está abierto; si no, HTTP
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      try {
        // Enviar JSON si tenemos contexto de fase, para que el backend lo reciba
        if (phase) {
          wsRef.current.send(JSON.stringify({ message: text, phase }))
        } else {
          wsRef.current.send(text)
        }
      } catch (e) {
        // Fallback a texto plano
        wsRef.current.send(text)
      }
    } else {
      try {
  const payload = { session_id: sessionId, message: text }
  if (phase) payload.phase = phase
  const { data } = await axios.post(`${apiBase}/chat/message`, payload, { headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) }, timeout: 5000 })
        
        // Check if we already have a complete proposal message
        // If so, ignore any subsequent messages from the backend
        const hasCompleteProposal = messagesRef.current.some(m => 
          m.role === 'assistant' && 
          typeof m.content === 'string' && 
          m.content.includes('✅ He cargado') && 
          m.content.includes('empleados de tu base de datos') &&
          m.content.includes('Asignación por rol') &&
          m.content.includes('¿Quieres comenzar el proyecto ahora?')
        )
        
        if (!hasCompleteProposal) {
          setMessages(prev => [...prev, { role: 'assistant', content: data.reply, ts: new Date().toISOString() }])
        }
      } catch (e) {
        const msg = e?.response?.data?.detail || e?.message || 'Error enviando mensaje.'
        setMessages(prev => [...prev, { role: 'assistant', content: `⚠️ ${msg}`, ts: new Date().toISOString() }])
      }
    }
  }

  // If parent passes an externalMessage + externalMessageId, send it once when the id changes.
  useEffect(() => {
    if (!externalMessage || !externalMessageId) return
    // send the provided text; send() will add the 'user' message and request a reply
    send(externalMessage)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [externalMessageId])

  const openExport = () => { setReportMeta(m => ({ ...m, session_id: sessionId })); setShowExport(true) }
  const doExport = async () => {
    if (!apiBase) { setMessages(prev => [...prev, { role: 'assistant', content: '⚠️ Backend no detectado. No puedo exportar el PDF.', ts: new Date().toISOString() }]); return }
    setLoadingExport(true)
    try {
      const payload = {
        title,
        report_meta: reportMeta,
        report_options: reportOptions,
        messages: messages.map(m => ({ role: m.role, content: m.content, ts: m.ts || new Date().toISOString(), name: m.name || undefined }))
      }
      const res = await axios.post(`${apiBase}/export/chat.pdf`, payload, { headers: { 'Content-Type': 'application/json' }, responseType: 'blob', timeout: 20000 })
      const blob = new Blob([res.data], { type: 'application/pdf' })
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      const ts = new Date().toISOString().replace(/[:.]/g, '-')
      a.href = url; a.download = `informe_${ts}.pdf`; document.body.appendChild(a); a.click(); a.remove()
      window.URL.revokeObjectURL(url)
      setShowExport(false)
    } catch (e) {
      const msg = e?.response?.data?.detail || e?.message || 'Error exportando PDF.'
      setMessages(prev => [...prev, { role: 'assistant', content: `⚠️ ${msg}`, ts: new Date().toISOString() }])
    } finally { setLoadingExport(false) }
  }

  // Auto-save helper used by CTA actions
  const saveChatIfNeeded = async (messagesToSave) => {
    try {
      let chatId = selectedChatId
      if (!chatId && onSaveCurrentChat) {
        console.log('[Chat] Auto-guardando nuevo chat (CTA)')
        chatId = await onSaveCurrentChat(messagesToSave, `Proyecto ${new Date().toLocaleString()}`)
        console.log('[Chat] Nuevo chat guardado con ID:', chatId)
      } else if (chatId && onSaveExistingChat) {
        console.log('[Chat] Actualizando chat existente (CTA):', chatId)
        await onSaveExistingChat(chatId, messagesToSave)
      }
    } catch (e) {
      console.error('Error guardando chat desde CTA:', e)
    }
  }

  // Handle CTA button clicks: send a predefined message and attempt to save
  const handleCta = async (type) => {
    try {
      if (type === 'view_pdf') {
        // Open export modal to let user generate/download the PDF
        openExport()
        setSuggestedCtas([])
        return
      }
      if (type === 'start') {
        // Replace 'start project' action with suggestion to export PDF
        setMessages(prev => [...prev, { role: 'assistant', content: 'Si quieres ver la propuesta completa antes de iniciar, pulsa "Exportar PDF" para descargarla.', ts: new Date().toISOString() }])
        setSuggestedCtas([{ type: 'view_pdf', label: 'Ver propuesta (PDF)' }])
        return
      }
      if (type === 'load_employees') {
        await loadEmployeesAndSend()
        setSuggestedCtas([])
        return
      }
      if (type === 'manual') {
        // send the 'manual' keyword to trigger assistant to ask for manual template
        await send('manual')
        const updated = [...messages, { role: 'user', content: 'manual', ts: new Date().toISOString() }]
        await saveChatIfNeeded(updated)
        setSuggestedCtas([])
        return
      }

      let text = ''
      if (type === 'accept') text = 'Acepto la propuesta'
      else if (type === 'start') text = 'Sí, vamos a comenzar el proyecto'
      else if (type === 'changes') text = 'Solicito cambios en la propuesta'
      else return

      await send(text)
      // Ensure the message is saved (either create or update)
      const updated = [...messages, { role: 'user', content: text, ts: new Date().toISOString() }]
      await saveChatIfNeeded(updated)
    } catch (e) {
      console.error('Error handling CTA:', e)
      setSuggestedCtas([])
    }
  }

  // Extract phases from an assistant message that includes methodology and phases
  const extractPhasesFromText = (raw) => {
    try {
      if (!raw) return []
      const txt = String(raw)
      // Try to find a 'Fases: ...' line produced by the proposal endpoint
      const fasesMatch = txt.match(/Fases:\s*([^\n\r]+)/i) || txt.match(/■\s*Fases:\s*([^\n\r]+)/i)
      if (!fasesMatch) return []
      const fasesStr = fasesMatch[1]
      // Split by common separators (arrow, ->, comma, semicolon)
      const parts = fasesStr.split(/→|->|,|;/).map(s => s.trim()).filter(Boolean)
      // Remove trailing week counts like '(3 semanas)'
      const phases = parts.map(p => p.replace(/\(.*?\)/g, '').trim()).filter(Boolean)
      return phases
    } catch (e) {
      return []
    }
  }

  const handlePhaseClick = async (phaseName) => {
    try {
      const text = `Sobre la fase: ${phaseName}`
      await send(text)
      const updated = [...messages, { role: 'user', content: text, ts: new Date().toISOString() }]
      await saveChatIfNeeded(updated)
    } catch (e) {
      console.error('Error handling phase click:', e)
    }
  }

  // Extract small paragraph descriptions for each phase from an assistant message
  const extractPhaseDefinitionsFromText = (raw, phases) => {
    try {
      const out = {}
      if (!raw || !phases || phases.length === 0) return out
      // split into paragraphs
      const paras = String(raw).split(/\n\s*\n/).map(p => p.trim()).filter(Boolean)
      phases.forEach(ph => {
        const re = new RegExp('\\b' + ph.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\$&') + '\\b', 'i')
        // find paragraph containing the phase name
        const found = paras.find(p => re.test(p))
        if (found) {
          out[ph] = found.length > 400 ? found.slice(0, 400) + '...' : found
        } else {
          // fallback: split into sentences without lookbehind
          const sentences = String(raw).match(/[^.!?]+[.!?]?/g) || []
          const s = sentences.find(s => re.test(s))
          out[ph] = s ? s.trim() : null
        }
      })
      return out
    } catch (e) {
      return {}
    }
  }

  // Load employees from backend and send JSON via WebSocket (mirrors earlier auto-load behavior)
  const loadEmployeesAndSend = async () => {
    if (!apiBase) {
      setMessages(prev => [...prev, { role: 'assistant', content: '⚠️ Backend no detectado. Arranca uvicorn en :8000.', ts: new Date().toISOString() }])
      return
    }

    try {
      const headers = token ? { Authorization: `Bearer ${token}` } : {}
      const { data } = await axios.get(`${apiBase}/user/employees`, { headers })
      if (Array.isArray(data) && data.length > 0) {
        const employeesJson = data.map(emp => ({
          name: emp.name,
          role: emp.role,
          skills: emp.skills,
          seniority: emp.seniority || 'Mid',
          availability_pct: emp.availability_pct || 100
        }))
        const jsonString = JSON.stringify(employeesJson, null, 2)

        // NO mostrar mensajes intermedios - enviar directamente
        // First, send a textual trigger so the backend sets the "awaiting_employees_data" context
        try {
          // Enviar directamente sin mostrar el mensaje en el chat
          if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
            wsRef.current.send('cargar empleados')
          } else {
            // HTTP fallback
            const payload = { session_id: sessionId, message: 'cargar empleados' }
            await axios.post(`${apiBase}/chat/message`, payload, { 
              headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) }, 
              timeout: 5000 
            })
          }
        } catch (e) {
          // ignore send errors here; we'll still attempt to deliver the JSON
        }

        // Wait briefly for the backend to be ready, then send the JSON
        setTimeout(async () => {
          if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
            wsRef.current.send(jsonString)
          } else {
            // HTTP fallback
            try {
              const payload = { session_id: sessionId, message: jsonString }
              await axios.post(`${apiBase}/chat/message`, payload, { 
                headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) }, 
                timeout: 5000 
              })
            } catch (err) {
              console.error('Error sending employees JSON via HTTP:', err)
            }
          }
        }, 500)

      } else {
        setMessages(prev => [...prev, { role: 'assistant', content: '⚠️ No tienes empleados guardados en la sección "Empleados".', ts: new Date().toISOString() }])
      }
    } catch (error) {
      console.error('Error cargando empleados (CTA):', error)
      setMessages(prev => [...prev, { role: 'assistant', content: '⚠️ Error cargando empleados. Comprueba los permisos o inténtalo manualmente.', ts: new Date().toISOString() }])
    }
  }

  return (
    <div className="h-full flex flex-col gap-2 min-w-0 min-h-0 box-border text-[13px] relative overflow-hidden">
      {/* acciones superiores */}
      <div className="flex items-center justify-between">
        <div className="text-sm text-gray-500">Consejo: escribe <code className="px-1 py-[1px] rounded bg-gray-100 border">/propuesta: requisitos del cliente</code></div>
        {(onSaveCurrentChat || onSaveExistingChat) && (
          <div className="relative">
            <button className="px-3 py-2 border rounded-xl hover:bg-gray-50" onClick={() => setShowSaveDialog(true)}>
              {selectedChatId ? 'Guardar cambios' : 'Guardar proyecto'}
            </button>
            {showSaveDialog && (
              <div className="absolute right-0 mt-2 p-3 bg-white border rounded-xl shadow-lg w-80">
                <div className="mb-2 font-medium">Título del proyecto</div>
                <input className="w-full border rounded px-2 py-1 mb-2" value={saveTitle} onChange={(e)=>setSaveTitle(e.target.value)} placeholder="Título (opcional)" />
                <div className="flex justify-end gap-2">
                  <button className="px-2 py-1 border rounded" onClick={()=>{ setShowSaveDialog(false); setSaveTitle('') }}>Cancelar</button>
                  <button
                    className="px-2 py-1 bg-emerald-600 text-white rounded"
                    onClick={() => {
                      if (selectedChatId && onSaveExistingChat) {
                        onSaveExistingChat(selectedChatId, messages, saveTitle || null)
                      } else if (onSaveCurrentChat) {
                        onSaveCurrentChat(messages, saveTitle || null)
                      }
                      setShowSaveDialog(false); setSaveTitle('')
                    }}
                  >
                    Guardar
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
      {/* area wrapper: messages scroll + fixed input at bottom (flex layout) */}
      <div className="flex flex-col w-full min-h-0 h-full">
        <div ref={listRef} onScroll={handleScroll} className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden p-3 custom-scroll rounded-2xl border bg-gradient-to-b from-white to-gray-50 box-border flex flex-col">
          <div className="space-y-3 pb-4 flex flex-col">
            {messages.map((m, i) => (
              <div key={i} className={`box-border max-w-full md:max-w-[60%] break-words rounded-2xl px-3 py-2 shadow-sm ${m.role === 'user' ? 'ml-auto bg-blue-600 text-white' : 'bg-white border'}`}>
                <div className="whitespace-pre-wrap font-sans text-[12px] leading-relaxed break-words">{m.content}</div>
                {m.ts && <div className="text-[10px] opacity-60 mt-1">{new Date(m.ts).toLocaleString()}</div>}

                {/* Render CTA buttons and phase buttons for this assistant message (if any) */}
                {m.role === 'assistant' && (() => {
                  // Special case: when backend confirms that it has loaded employees
                  const loadedEmployeesRegex = /^✅\s*He cargado \d+ empleados de tu base de datos\.$/i
                  const isLoadedEmployeesMsg = typeof m.content === 'string' && loadedEmployeesRegex.test(m.content.trim())

                  if (isLoadedEmployeesMsg) {
                    // No mostrar ningún botón para el mensaje corto de empleados cargados
                    return null
                  }

                  // Special case: Long proposal message ending with "¿Quieres comenzar el proyecto ahora?"
                  // This is the complete proposal with employees, assignments, gaps, and phases
                  const isCompleteProposal = typeof m.content === 'string' && 
                    m.content.includes('✅ He cargado') && 
                    m.content.includes('empleados de tu base de datos') &&
                    m.content.includes('Asignación por rol') &&
                    m.content.includes('¿Quieres comenzar el proyecto ahora?')
                  
                  if (isCompleteProposal) {
                    // Show "Terminar proyecto" button
                    return (
                      <div className="mt-2 flex flex-col gap-2">
                        <div className="flex flex-wrap gap-2">
                          <button
                            className="px-3 py-1 rounded-md border bg-emerald-600 text-white hover:bg-emerald-700 text-sm"
                            onClick={() => {
                              setSuggestedCtas([])
                              setMessages(prev => [...prev, { role: 'assistant', content: '✅ Perfecto. Su proyecto está completamente configurado y listo.\n\nPuede proceder a descargar el PDF con toda la información de la propuesta pulsando el botón "Exportar PDF".', ts: new Date().toISOString() }])
                            }}
                          >
                            Terminar proyecto
                          </button>
                        </div>
                      </div>
                    )
                  }

                  const ctas = detectCtas(m.content)
                  const phases = extractPhasesFromText(m.content)
                  if (( !ctas || ctas.length === 0 ) && ( !phases || phases.length === 0 )) return null
                  return (
                    <div className="mt-2 flex flex-col gap-2">
                      {ctas && ctas.length > 0 && (
                        <div className="flex flex-wrap gap-2">
                          {ctas.map((c, idx) => (
                            <button key={idx} className="px-3 py-1 rounded-md border bg-white hover:bg-gray-50 text-sm" onClick={() => handleCta(c.type)}>
                              {c.label}
                            </button>
                          ))}
                        </div>
                      )}

                      {phases && phases.length > 0 && (
                        <div className="flex flex-wrap gap-2">
                          {phases.map((p, idx) => (
                            <button key={`phase-${idx}`} className="px-3 py-1 rounded-md border bg-sky-50 hover:bg-sky-100 text-sm" onClick={() => handlePhaseClick(p)}>
                              {p}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  )
                })()}
              </div>
            ))}
          </div>
        </div>

        {/* CTA buttons suggested by assistant */}
        {suggestedCtas && suggestedCtas.length > 0 && (
          <div className="w-full flex gap-2 items-center mb-2">
            {suggestedCtas.map((c, idx) => (
              <button key={idx} className="px-3 py-2 rounded-xl border bg-white hover:bg-gray-50" onClick={() => handleCta(c.type)}>
                {c.label}
              </button>
            ))}
          </div>
        )}

        <div className="flex items-center gap-2 mt-3 flex-shrink-0 w-full">
          <input
            className="flex-1 min-w-0 border rounded-2xl px-3 h-10"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Escribe… (o /propuesta: requisitos del cliente)"
            onKeyDown={(e) => (e.key === 'Enter' ? send() : null)}
          />
          <div className="flex-shrink-0 flex items-center gap-2">
            <button className="px-4 py-2 rounded-2xl bg-blue-600 text-white hover:opacity-90" onClick={send}>Enviar</button>
            <button className="px-4 py-2 rounded-2xl bg-emerald-600 text-white hover:opacity-90" onClick={openExport}>Exportar PDF</button>
          </div>
        </div>
      </div>

      {/* modal export */}
      {showExport && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white w-full max-w-2xl rounded-2xl shadow-xl p-5 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold">Opciones de exportación</h2>
              <button className="text-gray-500 hover:text-gray-700" onClick={() => setShowExport(false)}>✕</button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label className="text-sm text-gray-600">Título del informe</label>
                <input className="w-full border rounded px-2 py-1" value={title} onChange={e => setTitle(e.target.value)} />
              </div>
              <div>
                <label className="text-sm text-gray-600">Subtítulo</label>
                <input className="w-full border rounded px-2 py-1" value={reportMeta.subtitle} onChange={e => setReportMeta(m => ({...m, subtitle: e.target.value}))} />
              </div>
              <div>
                <label className="text-sm text-gray-600">Proyecto</label>
                <input className="w-full border rounded px-2 py-1" value={reportMeta.project} onChange={e => setReportMeta(m => ({...m, project: e.target.value}))} />
              </div>
              <div>
                <label className="text-sm text-gray-600">Cliente</label>
                <input className="w-full border rounded px-2 py-1" value={reportMeta.client} onChange={e => setReportMeta(m => ({...m, client: e.target.value}))} />
              </div>
              <div>
                <label className="text-sm text-gray-600">Autor</label>
                <input className="w-full border rounded px-2 py-1" value={reportMeta.author} onChange={e => setReportMeta(m => ({...m, author: e.target.value}))} />
              </div>
              <div>
                <label className="text-sm text-gray-600">ID de sesión</label>
                <input className="w-full border rounded px-2 py-1" value={reportMeta.session_id} onChange={e => setReportMeta(m => ({...m, session_id: e.target.value}))} />
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div className="space-y-2">
                <label className="block text-sm text-gray-600">Secciones a incluir</label>
                <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={reportOptions.include_cover} onChange={e => setReportOptions(o => ({...o, include_cover: e.target.checked}))} /> Portada</label>
                <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={reportOptions.include_transcript} onChange={e => setReportOptions(o => ({...o, include_transcript: e.target.checked}))} /> Transcripción completa (Parte A)</label>
                <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={reportOptions.include_analysis} onChange={e => setReportOptions(o => ({...o, include_analysis: e.target.checked}))} /> Análisis narrativo (Parte B)</label>
                <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={reportOptions.include_final_proposal} onChange={e => setReportOptions(o => ({...o, include_final_proposal: e.target.checked}))} /> Propuesta final completa (Parte C)</label>
              </div>

              <div className="space-y-2">
                <label className="block text-sm text-gray-600">Profundidad del análisis</label>
                <select className="w-full border rounded px-2 py-1" value={reportOptions.analysis_depth} onChange={e => setReportOptions(o => ({...o, analysis_depth: e.target.value}))}>
                  <option value="brief">Breve</option>
                  <option value="standard">Estándar</option>
                  <option value="deep">Profundo</option>
                </select>

                <label className="block text-sm text-gray-600 mt-2">Tipografía</label>
                <select className="w-full border rounded px-2 py-1" value={reportOptions.font_name} onChange={e => setReportOptions(o => ({...o, font_name: e.target.value}))}>
                  <option value="Helvetica">Helvetica (corporativo)</option>
                  <option value="Times New Roman">Times New Roman</option>
                  <option value="Courier">Courier (monoespaciada)</option>
                </select>
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-2">
              <button className="px-3 py-2 rounded-xl border" onClick={() => setShowExport(false)}>Cancelar</button>
              <button className="px-4 py-2 rounded-xl bg-emerald-600 text-white disabled:opacity-50" onClick={doExport} disabled={loadingExport}>
                {loadingExport ? 'Generando…' : 'Generar PDF'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
