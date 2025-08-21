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
    try {
      await axios.get(`${base}/health`, { timeout: 1500 })
      return base
    } catch { /* prueba el siguiente */ }
  }
  return null
}

export default function Chat() {
  const [apiBase, setApiBase] = useState(null)
  const [sessionId] = useState(() => 'demo-' + Math.random().toString(36).slice(2, 8))
  const [messages, setMessages] = useState([
    { role: 'assistant', content: '👋 Hola, soy el asistente (Parte 1). Pídeme una propuesta o escribe cualquier cosa.' }
  ])
  const [input, setInput] = useState('')
  const wsRef = useRef(null)
  const listRef = useRef(null)

  // Descubre el backend y abre WebSocket si es posible
  useEffect(() => {
    (async () => {
      const base = await detectApiBase()
      if (!base) {
        setMessages(prev => [...prev, { role: 'assistant', content: '⚠️ No encuentro el backend en :8000. Asegúrate de arrancar: uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000' }])
        return
      }
      setApiBase(base)

      try {
        const u = new URL(base)
        const proto = u.protocol === 'https:' ? 'wss' : 'ws'
        const wsUrl = `${proto}://${u.host}/chat/ws?session_id=${sessionId}`
        const ws = new WebSocket(wsUrl)
        wsRef.current = ws
        ws.onmessage = (evt) => setMessages(prev => [...prev, { role: 'assistant', content: evt.data }])
        ws.onerror = () => setMessages(prev => [...prev, { role: 'assistant', content: '⚠️ No se pudo conectar por WebSocket. Usaré HTTP.' }])
      } catch {
        setMessages(prev => [...prev, { role: 'assistant', content: '⚠️ No se pudo conectar por WebSocket. Usaré HTTP.' }])
      }
    })()
  }, [sessionId])

  useEffect(() => {
    if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight
  }, [messages])

  const send = async () => {
    const text = input.trim()
    if (!text) return
    setMessages(prev => [...prev, { role: 'user', content: text }])
    setInput('')

    if (!apiBase) {
      setMessages(prev => [...prev, { role: 'assistant', content: '⚠️ Backend no detectado. ¿Arrancaste uvicorn en :8000?' }])
      return
    }

    // Comando de propuesta
    if (text.toLowerCase().startsWith('/propuesta:')) {
      const req = text.split(':').slice(1).join(':').trim() || 'Proyecto genérico'
      try {
        const { data } = await axios.post(`${apiBase}/projects/proposal`, {
          session_id: sessionId,
          requirements: req
        }, { headers: { 'Content-Type': 'application/json' }, timeout: 5000 })
        const pretty = [
          `📌 Metodología: ${data.methodology}`,
          `👥 Equipo: ${data.team.map(t => `${t.role} x${t.count}`).join(', ')}`,
          `🧩 Fases: ${data.phases.map(p => `${p.name} (${p.weeks} semanas)`).join(' → ')}`,
          `💶 Presupuesto: ${data.budget.total_eur} €`,
          `⚠️ Riesgos: ${data.risks.join('; ')}`,
        ].join('\n')
        setMessages(prev => [...prev, { role: 'assistant', content: pretty }])
      } catch (e) {
        const msg = e?.response?.data?.detail || e?.message || 'Error obteniendo la propuesta.'
        setMessages(prev => [...prev, { role: 'assistant', content: `⚠️ ${msg}` }])
      }
      return
    }

    // WS si está abierto; si no, HTTP
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(text)
    } else {
      try {
        const { data } = await axios.post(`${apiBase}/chat/message`, {
          session_id: sessionId,
          message: text
        }, { headers: { 'Content-Type': 'application/json' }, timeout: 5000 })
        setMessages(prev => [...prev, { role: 'assistant', content: data.reply }])
      } catch (e) {
        const msg = e?.response?.data?.detail || e?.message || 'Error enviando mensaje.'
        setMessages(prev => [...prev, { role: 'assistant', content: `⚠️ ${msg}` }])
      }
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div ref={listRef} className="h-96 overflow-y-auto space-y-2 border rounded-lg p-3 bg-gray-50">
        {messages.map((m, i) => (
          <div key={i} className={`max-w-[85%] rounded-xl px-3 py-2 ${m.role === 'user' ? 'ml-auto bg-blue-600 text-white' : 'bg-white border'}`}>
            <pre className="whitespace-pre-wrap font-sans text-sm">{m.content}</pre>
          </div>
        ))}
      </div>
      <div className="flex gap-2">
        <input
          className="flex-1 border rounded-lg px-3 py-2"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Escribe… (o /propuesta: requisitos del cliente)"
          onKeyDown={(e) => (e.key === 'Enter' ? send() : null)}
        />
        <button className="px-4 py-2 rounded-lg bg-blue-600 text-white" onClick={send}>Enviar</button>
      </div>
      <p className="text-xs text-gray-500">
        Comando: <code>/propuesta: App móvil de reservas con pagos</code>
      </p>
    </div>
  )
}
