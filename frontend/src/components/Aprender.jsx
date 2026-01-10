import React, { useState } from 'react'
import axios from 'axios'

export default function Aprender({ token }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [sessionId] = useState(() => `learn_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`)
  const [trainingActive, setTrainingActive] = useState(false)
  const [selectedLevel, setSelectedLevel] = useState(null)
  const [selectedMethodology, setSelectedMethodology] = useState(null)

  const base = `http://${window.location.hostname}:8000`
  
  const topics = [
    { name: '¿Qué es?', icon: '❓', question: '¿Qué es {method}?' },
    { name: 'Roles típicos', icon: '👥', question: '¿Cuáles son los roles típicos en {method}?' },
    { name: 'Prácticas clave', icon: '⚡', question: '¿Cuáles son las prácticas clave de {method}?' },
    { name: 'Fases', icon: '🔄', question: '¿Cuáles son las fases de {method}?' },
    { name: 'Ceremonias', icon: '📅', question: '¿Qué ceremonias se usan en {method}?' },
    { name: 'Artefactos', icon: '📋', question: '¿Qué artefactos se usan en {method}?' },
    { name: 'Métricas', icon: '📊', question: '¿Qué métricas se usan en {method}?' },
    { name: 'Cuándo usar', icon: '✅', question: '¿Cuándo es mejor usar {method}?' },
    { name: 'Cuándo evitar', icon: '❌', question: '¿Cuándo debería evitar usar {method}?' },
    { name: 'Ventajas', icon: '➕', question: '¿Cuáles son las ventajas de {method}?' },
    { name: 'Desventajas', icon: '➖', question: '¿Cuáles son las desventajas de {method}?' },
    { name: 'Ejemplos prácticos', icon: '💡', question: 'Dame ejemplos prácticos de {method}' }
  ]
  
  const methodologies = [
    { name: 'Scrum', icon: '🔄', description: 'Marco para gestión de proyectos con sprints' },
    { name: 'Kanban', icon: '📊', description: 'Método visual de gestión de flujo continuo' },
    { name: 'XP (Extreme Programming)', icon: '⚡', description: 'Prácticas técnicas para alta calidad' },
    { name: 'Lean', icon: '🎯', description: 'Eliminar desperdicio y acelerar aprendizaje' },
    { name: 'SAFe', icon: '🏢', description: 'Framework ágil para grandes organizaciones' },
    { name: 'Scrumban', icon: '🔀', description: 'Híbrido entre Scrum y Kanban' },
    { name: 'Crystal', icon: '💎', description: 'Familia de metodologías adaptables' },
    { name: 'FDD', icon: '🎨', description: 'Feature-Driven Development' }
  ]

  // Iniciar modo aprendizaje con metodología y tema específico
  const startLearningWithTopic = async (methodology, topic) => {
    setLoading(true)
    try {
      // Primero activar modo aprendizaje
      await axios.post(`${base}/chat/message`, {
        session_id: sessionId,
        message: 'aprender'
      }, {
        headers: { 'Content-Type': 'application/json' }
      })
      
      // Luego enviar el nivel
      await axios.post(`${base}/chat/message`, {
        session_id: sessionId,
        message: selectedLevel
      }, {
        headers: { 'Content-Type': 'application/json' }
      })
      
      // Finalmente preguntar sobre el tema específico
      const question = topic.question.replace('{method}', methodology)
      const { data } = await axios.post(`${base}/chat/message`, {
        session_id: sessionId,
        message: question
      }, {
        headers: { 'Content-Type': 'application/json' }
      })
      
      console.log('Respuesta del backend:', data)
      
      // Extraer el contenido de la respuesta
      let responseContent = ''
      if (typeof data === 'string') {
        // Intentar parsear si es un string JSON
        try {
          const parsed = JSON.parse(data)
          responseContent = parsed.reply || parsed.response || parsed.content || data
        } catch {
          responseContent = data
        }
      } else if (data.reply) {
        responseContent = data.reply
      } else if (data.response) {
        responseContent = data.response
      } else if (data.content) {
        responseContent = data.content
      } else {
        responseContent = JSON.stringify(data)
      }
      
      // Limpiar metadata que pueda venir en el contenido
      responseContent = responseContent.replace(/\{"reply":"(.+?)","debug".+?\}/g, '$1')
      responseContent = responseContent.replace(/\\n/g, '\n')
      // Eliminar frases de navegación del modo formación
      responseContent = responseContent.replace(/Puedes pedir[^.]*\./g, '')
      responseContent = responseContent.replace(/Puedes escribir[^.]*\./g, '')
      responseContent = responseContent.replace(/Pide[^.]*\./g, '')
      responseContent = responseContent.trim()
      
      // Solo mostrar la pregunta del usuario y la respuesta del asistente
      const userMsg = { role: 'user', content: question, ts: new Date().toISOString() }
      const assistantMsg = { role: 'assistant', content: responseContent, ts: new Date().toISOString() }
      
      setMessages([userMsg, assistantMsg])
      setTrainingActive(true)
    } catch (e) {
      console.error('start learning error', e)
      const errorContent = e?.response?.data?.detail || e.message || 'Error al cargar la información. Intenta de nuevo.'
      setMessages([{ role: 'assistant', content: errorContent, ts: new Date().toISOString() }])
    } finally {
      setLoading(false)
    }
  }

  const sendMessage = async () => {
    const msg = input.trim()
    if (!msg || loading) return

    setInput('')
    setLoading(true)

    try {
      const { data } = await axios.post(`${base}/chat/message`, {
        session_id: sessionId,
        message: msg
      }, {
        headers: { 'Content-Type': 'application/json' }
      })

      // Extraer contenido
      let responseContent = ''
      if (typeof data === 'string') {
        responseContent = data
      } else if (data.response) {
        responseContent = data.response
      } else if (data.content) {
        responseContent = data.content
      } else {
        responseContent = JSON.stringify(data)
      }

      const assistantMsg = { role: 'assistant', content: responseContent, ts: new Date().toISOString() }
      setMessages(prev => [...prev, assistantMsg])

      // Detectar si salió del modo formación
      if (responseContent && responseContent.toLowerCase().includes('salido del modo')) {
        setTrainingActive(false)
      }
    } catch (e) {
      console.error('send message error', e)
      const errorContent = e?.response?.data?.detail || e.message || 'Error al procesar el mensaje.'
      const errorMsg = { role: 'assistant', content: errorContent, ts: new Date().toISOString() }
      setMessages(prev => [...prev, errorMsg])
    } finally {
      setLoading(false)
    }
  }

  const resetLearning = () => {
    setMessages([])
    setInput('')
    setTrainingActive(false)
    setSelectedLevel(null)
    setSelectedMethodology(null)
  }

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="rounded-2xl p-4 bg-white/70 backdrop-blur border shadow-sm mb-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold mb-1 flex items-center gap-2">
              <span className="text-2xl">🎓</span> Modo Aprendizaje
            </h2>
            <p className="text-sm text-gray-600">
              Aprende sobre metodologías ágiles de forma interactiva: Scrum, Kanban, XP, Lean y más.
            </p>
          </div>
          {messages.length > 0 && (
            <button
              onClick={resetLearning}
              className="px-4 py-2 rounded-xl border hover:bg-gray-50 text-sm"
            >
              Reiniciar
            </button>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden flex flex-col">
        {messages.length === 0 && !loading ? (
          // Pantalla inicial
          <div className="flex-1 flex flex-col p-8">
            <div className="w-full space-y-4">
              {!selectedLevel ? (
                <>
                  <div className="text-center mb-6">
                    <div className="text-4xl mb-2">📚</div>
                    <h3 className="text-xl font-bold text-gray-800">Modo Aprendizaje</h3>
                    <p className="text-sm text-gray-600 mt-1">
                      Selecciona tu nivel de conocimiento
                    </p>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4 max-w-3xl mx-auto">
                    <button
                      onClick={() => setSelectedLevel('principiante')}
                      className="bg-blue-50 rounded-xl p-6 hover:bg-blue-100 transition cursor-pointer border-2 border-transparent hover:border-blue-400"
                    >
                      <div className="text-3xl mb-2">🌱</div>
                      <h4 className="font-semibold text-blue-900 mb-1">Principiante</h4>
                      <p className="text-xs text-blue-700">Conceptos básicos y fundamentos</p>
                    </button>
                    <button
                      onClick={() => setSelectedLevel('intermedio')}
                      className="bg-purple-50 rounded-xl p-6 hover:bg-purple-100 transition cursor-pointer border-2 border-transparent hover:border-purple-400"
                    >
                      <div className="text-3xl mb-2">🚀</div>
                      <h4 className="font-semibold text-purple-900 mb-1">Intermedio</h4>
                      <p className="text-xs text-purple-700">Prácticas y casos de uso</p>
                    </button>
                    <button
                      onClick={() => setSelectedLevel('experto')}
                      className="bg-emerald-50 rounded-xl p-6 hover:bg-emerald-100 transition cursor-pointer border-2 border-transparent hover:border-emerald-400"
                    >
                      <div className="text-3xl mb-2">⭐</div>
                      <h4 className="font-semibold text-emerald-900 mb-1">Experto</h4>
                      <p className="text-xs text-emerald-700">Estrategias avanzadas</p>
                    </button>
                  </div>
                </>
              ) : (
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <div className="bg-emerald-50 border border-emerald-200 rounded-lg px-4 py-2">
                      <p className="text-emerald-900 font-semibold text-sm">
                        Nivel: <span className="capitalize">{selectedLevel}</span>
                        {selectedMethodology && <span> • {selectedMethodology}</span>}
                      </p>
                    </div>
                    <button
                      onClick={() => {
                        setSelectedLevel(null)
                        setSelectedMethodology(null)
                      }}
                      className="px-3 py-1 text-xs text-gray-600 hover:text-gray-800 underline"
                    >
                      ← Volver al inicio
                    </button>
                  </div>

                  {!selectedMethodology ? (
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                      {methodologies.map((method, i) => (
                        <button
                          key={i}
                          onClick={() => setSelectedMethodology(method.name)}
                          disabled={loading}
                          className="bg-white rounded-xl p-4 border-2 border-gray-200 hover:border-emerald-400 hover:bg-emerald-50 transition disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          <div className="flex flex-col items-center text-center gap-2">
                            <span className="text-3xl">{method.icon}</span>
                            <h4 className="font-semibold text-gray-900 text-sm">{method.name}</h4>
                            <p className="text-xs text-gray-600">{method.description}</p>
                          </div>
                        </button>
                      ))}
                    </div>
                  ) : (
                    <div className="space-y-3">
                      <div className="flex items-center justify-between">
                        <h3 className="text-lg font-semibold text-gray-800">
                          ¿Qué quieres aprender sobre {selectedMethodology}?
                        </h3>
                        <button
                          onClick={() => setSelectedMethodology(null)}
                          className="px-3 py-1 text-xs text-gray-600 hover:text-gray-800 underline"
                        >
                          ← Cambiar metodología
                        </button>
                      </div>
                      {loading ? (
                        <div className="flex justify-center items-center py-12">
                          <div className="text-center">
                            <div className="animate-spin rounded-full h-12 w-12 border-4 border-emerald-600 border-t-transparent mx-auto mb-4"></div>
                            <p className="text-gray-600">Cargando información...</p>
                          </div>
                        </div>
                      ) : (
                        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
                          {topics.map((topic, i) => (
                            <button
                              key={i}
                              onClick={() => startLearningWithTopic(selectedMethodology, topic)}
                              disabled={loading}
                              className="bg-white rounded-xl p-3 border-2 border-gray-200 hover:border-blue-400 hover:bg-blue-50 transition disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                              <div className="flex flex-col items-center text-center gap-2">
                                <span className="text-2xl">{topic.icon}</span>
                                <h4 className="font-medium text-gray-900 text-xs">{topic.name}</h4>
                              </div>
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        ) : (
          // Mostrar información - vista de contenido simple sin interacción
          <>
            {loading && messages.length === 0 ? (
              <div className="flex-1 flex items-center justify-center">
                <div className="text-center">
                  <div className="animate-spin rounded-full h-16 w-16 border-4 border-emerald-600 border-t-transparent mx-auto mb-4"></div>
                  <p className="text-gray-600 font-medium">Cargando información...</p>
                </div>
              </div>
            ) : (
      <div className="flex-1 overflow-y-auto pr-2 custom-scroll">
                <div className="max-w-4xl mx-auto space-y-6 p-4">
                  {/* Mostrar solo las respuestas del asistente */}
                  {messages.filter(msg => msg.role === 'assistant').map((msg, i) => {
                    // Limpiar y formatear el contenido
                    let content = msg.content
                    
                    // Limpiar JSON si viene embebido
                    content = content.replace(/\{"reply":"(.+?)","debug".+?\}/g, '$1')
                    content = content.replace(/\\n/g, '\n')
                    
                    // Separar en líneas para formatear
                    const lines = content.split('\n').filter(line => line.trim())
                    
                    return (
                      <div key={i} className="bg-gradient-to-br from-white to-blue-50 rounded-2xl p-8 border-2 border-blue-100 shadow-lg">
                        <div className="space-y-4">
                          {lines.map((line, idx) => {
                            const trimmed = line.trim()
                            
                            // Título principal (primera línea o con —)
                            if (idx === 0 || trimmed.includes('—')) {
                              return (
                                <div key={idx} className="border-b-2 border-blue-200 pb-3 mb-4">
                                  <h3 className="text-2xl font-bold text-blue-900 flex items-center gap-3">
                                    <span className="text-3xl">📚</span>
                                    {trimmed.replace(/^[-–—]\s*/, '')}
                                  </h3>
                                </div>
                              )
                            }
                            
                            // Secciones con bullet points
                            if (trimmed.startsWith('-') || trimmed.startsWith('•')) {
                              const text = trimmed.replace(/^[-•]\s*/, '')
                              return (
                                <div key={idx} className="flex items-start gap-3 ml-4">
                                  <span className="text-emerald-600 text-xl mt-1">✓</span>
                                  <p className="text-gray-800 text-base leading-relaxed flex-1">{text}</p>
                                </div>
                              )
                            }
                            
                            // Subtítulos (con : al final o en mayúsculas)
                            if (trimmed.endsWith(':') || (trimmed === trimmed.toUpperCase() && trimmed.length > 3 && trimmed.length < 50)) {
                              return (
                                <div key={idx} className="mt-6 mb-3">
                                  <h4 className="text-lg font-semibold text-blue-800 flex items-center gap-2">
                                    <span className="text-xl">💡</span>
                                    {trimmed}
                                  </h4>
                                </div>
                              )
                            }
                            
                            // Párrafos normales
                            if (trimmed.length > 0) {
                              return (
                                <p key={idx} className="text-gray-700 text-base leading-relaxed">
                                  {trimmed}
                                </p>
                              )
                            }
                            
                            return null
                          })}
                        </div>
                      </div>
                    )
                  })}
                  
                  {loading && messages.length > 0 && (
                    <div className="bg-white rounded-xl p-6 border shadow-sm">
                      <div className="flex items-center gap-3">
                        <div className="animate-spin rounded-full h-5 w-5 border-2 border-emerald-600 border-t-transparent"></div>
                        <span className="text-gray-600">Cargando más información...</span>
                      </div>
                    </div>
                  )}

                  {/* Botones de navegación */}
                  <div className="flex gap-3 justify-center pt-4">
                    <button
                      onClick={() => {
                        setMessages([])
                      }}
                      className="px-6 py-3 bg-blue-600 text-white rounded-xl font-semibold hover:bg-blue-700 transition shadow-md"
                    >
                      ← Ver otros temas de {selectedMethodology}
                    </button>
                    <button
                      onClick={resetLearning}
                      className="px-6 py-3 border-2 border-gray-300 text-gray-700 rounded-xl font-semibold hover:bg-gray-50 transition shadow-md"
                    >
                      🏠 Volver al inicio
                    </button>
                  </div>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
