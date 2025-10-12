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

export default function Chat({ token, loadedMessages = null, onSaveCurrentChat = null, sessionId: externalSessionId = null }) {
  const [apiBase, setApiBase] = useState(null)
  const [sessionId, setSessionId] = useState(() => 'demo-' + Math.random().toString(36).slice(2, 8))
  const [messages, setMessages] = useState([
    { role: 'assistant', content: '👋 Hola, soy el asistente (Parte 1). Pídeme una propuesta o escribe cualquier cosa.', ts: new Date().toISOString() }
  ])
  const [input, setInput] = useState('')
  const wsRef = useRef(null)
  const listRef = useRef(null)
  const [showSaveDialog, setShowSaveDialog] = useState(false)
  const [saveTitle, setSaveTitle] = useState('')

  // export dialog
  const [showExport, setShowExport] = useState(false)
  const [loadingExport, setLoadingExport] = useState(false)
  const [title, setTitle] = useState('Informe de la conversación')
  const [reportMeta, setReportMeta] = useState({ project:'', client:'', author:'', session_id:'', subtitle:'Chat + decisiones + propuesta final' })
  const [reportOptions, setReportOptions] = useState({ include_cover:true, include_transcript:true, include_analysis:true, include_final_proposal:true, analysis_depth:'deep', font_name:'Helvetica' })

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
        ws.onmessage = (evt) =>
          setMessages(prev => [...prev, { role: 'assistant', content: evt.data, ts: new Date().toISOString() }])
        ws.onerror = () =>
          setMessages(prev => [...prev, { role: 'assistant', content: '⚠️ No se pudo conectar por WebSocket. Usaré HTTP.', ts: new Date().toISOString() }])
      } catch {
        setMessages(prev => [...prev, { role: 'assistant', content: '⚠️ No se pudo conectar por WebSocket. Usaré HTTP.', ts: new Date().toISOString() }])
      }
    })()
  }, [sessionId])

  useEffect(()=>{ if(externalSessionId){ setSessionId(externalSessionId) } }, [externalSessionId])
  useEffect(() => { if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight }, [messages])
  useEffect(()=>{ if(Array.isArray(loadedMessages) && loadedMessages.length){ setMessages(loadedMessages.map(m => ({ role: m.role, content: m.content, ts: m.ts || new Date().toISOString() }))) } }, [loadedMessages])

  const send = async () => {
    const text = input.trim()
    if (!text) return
    setMessages(prev => [...prev, { role: 'user', content: text, ts: new Date().toISOString() }])
    setInput('')

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
      wsRef.current.send(text)
    } else {
      try {
        const { data } = await axios.post(`${apiBase}/chat/message`, { session_id: sessionId, message: text }, { headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) }, timeout: 5000 })
        setMessages(prev => [...prev, { role: 'assistant', content: data.reply, ts: new Date().toISOString() }])
      } catch (e) {
        const msg = e?.response?.data?.detail || e?.message || 'Error enviando mensaje.'
        setMessages(prev => [...prev, { role: 'assistant', content: `⚠️ ${msg}`, ts: new Date().toISOString() }])
      }
    }
  }

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

  return (
    <div className="h-full flex flex-col gap-3">
      {/* acciones superiores */}
      <div className="flex items-center justify-between">
        <div className="text-sm text-gray-500">Consejo: escribe <code className="px-1 py-[1px] rounded bg-gray-100 border">/propuesta: requisitos del cliente</code></div>
        {onSaveCurrentChat && (
          <div className="relative">
            <button className="px-3 py-2 border rounded-xl hover:bg-gray-50" onClick={() => setShowSaveDialog(true)}>Guardar chat</button>
            {showSaveDialog && (
              <div className="absolute right-0 mt-2 p-3 bg-white border rounded-xl shadow-lg w-80">
                <div className="mb-2 font-medium">Título del chat</div>
                <input className="w-full border rounded px-2 py-1 mb-2" value={saveTitle} onChange={(e)=>setSaveTitle(e.target.value)} placeholder="Título (opcional)" />
                <div className="flex justify-end gap-2">
                  <button className="px-2 py-1 border rounded" onClick={()=>{ setShowSaveDialog(false); setSaveTitle('') }}>Cancelar</button>
                  <button className="px-2 py-1 bg-emerald-600 text-white rounded" onClick={()=>{ onSaveCurrentChat(messages, saveTitle || null); setShowSaveDialog(false); setSaveTitle('') }}>Guardar</button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* área de mensajes */}
      <div ref={listRef} className="flex-1 overflow-y-auto custom-scroll rounded-2xl border bg-gradient-to-b from-white to-gray-50 p-4">
        <div className="space-y-3">
          {messages.map((m, i) => (
            <div key={i} className={`max-w-[85%] rounded-2xl px-3 py-2 shadow-sm ${m.role === 'user' ? 'ml-auto bg-blue-600 text-white' : 'bg-white border'}`}>
              <pre className="whitespace-pre-wrap font-sans text-[13px] leading-relaxed">{m.content}</pre>
              {m.ts && <div className="text-[10px] opacity-60 mt-1">{new Date(m.ts).toLocaleString()}</div>}
            </div>
          ))}
        </div>
      </div>

      {/* entrada */}
      <div className="flex items-center gap-2">
        <input
          className="flex-1 border rounded-2xl px-3 py-2"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Escribe… (o /propuesta: requisitos del cliente)"
          onKeyDown={(e) => (e.key === 'Enter' ? send() : null)}
        />
        <button className="px-4 py-2 rounded-2xl bg-blue-600 text-white hover:opacity-90" onClick={send}>Enviar</button>
        <button className="px-4 py-2 rounded-2xl bg-emerald-600 text-white hover:opacity-90" onClick={openExport}>Exportar PDF</button>
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
