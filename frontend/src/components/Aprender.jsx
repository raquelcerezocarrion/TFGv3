import React, { useState } from 'react'
import axios from 'axios'
import { API_BASE } from '../api'

export default function Aprender({ token }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [sessionId] = useState(() => `learn_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`)
  const [trainingActive, setTrainingActive] = useState(false)
  const [selectedLevel, setSelectedLevel] = useState(null)
  const [selectedMethodology, setSelectedMethodology] = useState(null)

  const base = API_BASE
  
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

      // Contenido estático por metodología y tema (se usa en lugar de llamadas al backend)
      const staticContent = {
        Scrum: {
          '¿Qué es?': `Scrum — ¿qué es y cuándo usarla?

Marco ágil con sprints cortos para entregar valor frecuente.

Prácticas clave: Sprints, Daily, Review, Retros, Product Backlog, Definition of Done

Evitar si: Plazos y alcance rígidos sin margen de negociación; Necesidad de operación 24/7 con interrupciones constantes`,
          'Roles típicos': `Scrum — Roles típicos

- Product Owner: Responsable del backlog y prioridades.
- Scrum Master: Facilita al equipo y elimina impedimentos.
- Equipo de desarrollo: Autogestionado y multifuncional.`,
          'Prácticas clave': `Scrum — Prácticas clave

- Sprints cortos y cadenciados
- Revisión de incremento (Review)
- Retrospectiva para mejora continua
- Refinamiento de backlog
- Definition of Done (DoD)`,
          'Fases': `Scrum — Fases (flujo)

- Planificación de sprint (Sprint Planning)
- Ejecución del sprint
- Revisión del sprint (Review)
- Retrospectiva (Retro)
- Preparación/refinamiento del backlog`,
          'Ceremonias': `Scrum — Ceremonias

- Daily Standup (Daily)
- Sprint Planning
- Sprint Review
- Sprint Retrospective
- Refinement (opcional y continuo)`,
          'Artefactos': `Scrum — Artefactos

- Product Backlog
- Sprint Backlog
- Incremento (deliverable que cumple DoD)
- Definition of Done`,
          'Métricas': `Scrum — Métricas comunes

- Velocidad (velocity)
- Burndown chart
- Tiempo de ciclo por ítem
- % de historias completadas vs comprometidas`,
          'Cuándo usar': `Scrum — Cuándo usarlo

- Proyectos con requerimientos que cambian frecuentemente
- Equipos que pueden trabajar en sprints iterativos
- Necesidad de feedback frecuente de stakeholders`,
          'Cuándo evitar': `Scrum — Cuándo evitarlo

- Operaciones 24/7 con interrupciones constantes
- Proyectos con alcance y requisitos completamente fijos y sin margen de negociación`,
          'Ventajas': `Scrum — Ventajas

- Entregas frecuentes de valor
- Mayor visibilidad y feedback temprano
- Mejora continua mediante retros`,
          'Desventajas': `Scrum — Desventajas

- Requiere disciplina y compromiso del equipo
- Puede ser ineficiente si hay muchas interrupciones
- Overhead de ceremonias si se aplica mal`,
          'Ejemplos prácticos': `Scrum — Ejemplos prácticos

- Equipo de producto que lanza releases cada 2 semanas
- Adaptación rápida a cambios de prioridad por el Product Owner
- Uso de retros para reducir defectos y mejorar estimaciones`,
        },
        Kanban: {
          '¿Qué es?': `Kanban — ¿qué es?

Kanban es un método visual para gestionar el flujo de trabajo en curso (WIP) mediante tarjetas y columnas. Ideal para equipos con flujo continuo y variabilidad en prioridades.`,
          'Roles típicos': `Kanban — Roles típicos

- No exige roles fijos; suelen existir responsables de flujo o propietarios de cola.
- Equipos operativos que gestionan tarjetas en el tablero.`,
          'Prácticas clave': `Kanban — Prácticas clave

- Visualizar trabajo en columnas
- Limitar WIP (Work In Progress)
- Medir flujo y mejorar cuellos de botella
- Pull system (extraer trabajo cuando hay capacidad)`,
          'Fases': `Kanban — Fases

- Backlog
- Ready
- In Progress
- Review/Testing
- Done

El flujo se adapta según el equipo.`,
          'Ceremonias': `Kanban — Ceremonias

- Reuniones de flujo/standups cortos
- Revisión de políticas del tablero
- Retrospectivas para mejora de flujo`,
          'Artefactos': `Kanban — Artefactos

- Tablero Kanban
- Tarjetas (historia/tarea)
- Políticas/criterios de entrada y salida`,
          'Métricas': `Kanban — Métricas

- Lead time
- Cycle time
- Throughput
- Work in progress (WIP)`,
          'Cuándo usar': `Kanban — Cuándo usarlo

- Operaciones o equipos con flujo continuo
- Donde las prioridades cambian frecuentemente y es necesario flexibilidad`,
          'Cuándo evitar': `Kanban — Cuándo evitarlo

- Proyectos que requieren entregas planificadas con fechas fijas y coordinar muchos equipos sin reglas de sincronización`,
          'Ventajas': `Kanban — Ventajas

- Alta flexibilidad
- Menor overhead de ceremonias
- Mejora continua del flujo`,
          'Desventajas': `Kanban — Desventajas

- Puede ser menos predecible en entregas con muchas prioridades
- Requiere disciplina para mantener límites WIP`,
          'Ejemplos prácticos': `Kanban — Ejemplos prácticos

- Equipo de soporte que procesa tickets continuamente
- Pipeline de despliegue donde las tareas fluyen según capacidad`,
        },
        'XP (Extreme Programming)': {
          '¿Qué es?': `XP — ¿qué es?

Conjunto de prácticas técnicas y de ingeniería para mejorar calidad: TDD, pair programming, integración continua, refactorización continua.`,
          'Roles típicos': `XP — Roles típicos

- Cliente (on-site): Define requisitos y pruebas.
- Equipo de desarrollo: Colabora estrechamente con prácticas técnicas.`,
          'Prácticas clave': `XP — Prácticas clave

- Programación en parejas (pair programming)
- Desarrollo guiado por pruebas (TDD)
- Integración continua
- Refactorización frecuente
- Propiedad colectiva del código`,
          'Fases': `XP — Fases

- Iteraciones cortas con entrega de historias
- Ciclo: escribir prueba → implementar → refactorizar`,
          'Ceremonias': `XP — Ceremonias

- Planning game (planificación colaborativa)
- Pequñas reuniones de sincronización y revisión de pruebas`,
          'Artefactos': `XP — Artefactos

- Suite de pruebas automatizadas
- Historias pequeñas y bien definidas
- Código con cobertura de tests`,
          'Métricas': `XP — Métricas

- Cobertura de tests
- Número de fallos en integración
- Tiempo para pasar la suite de tests`,
          'Cuándo usar': `XP — Cuándo usarlo

- Proyectos donde la calidad técnica es crítica
- Equipos con alta disciplina técnica`,
          'Cuándo evitar': `XP — Cuándo evitarlo

- Equipos sin soporte para prácticas técnicas o con plazos que impiden refactorizar y escribir tests`,
          'Ventajas': `XP — Ventajas

- Alta calidad del software
- Rápida detección de errores
- Código más mantenible`,
          'Desventajas': `XP — Desventajas

- Requiere alta disciplina técnica
- Curva de adopción y coste inicial en tiempo para tests`,
          'Ejemplos prácticos': `XP — Ejemplos prácticos

- Equipos que aplican TDD y pair programming en entregas críticas
- Ciclos rápidos con integración continua y despliegues frecuentes`,
        },
        Lean: {
          '¿Qué es?': `Lean — ¿qué es?

Enfoque en eliminar desperdicio, optimizar flujo y acelerar aprendizaje mediante entregas continuas y mejora de procesos.`,
          'Roles típicos': `Lean — Roles típicos

- Líderes de proceso y equipos cross-funcionales que identifican desperdicios.`,
          'Prácticas clave': `Lean — Prácticas clave

- Identificar y eliminar desperdicio
- Mejorar el flujo
- Entregar lo mínimo viable rápidamente
- Aprendizaje continuo`,
          'Fases': `Lean — Fases

- Identificar valor
- Mapear flujo de valor
- Crear flujo continuo
- Establecer pull
- Mejorar continuamente`,
          'Ceremonias': `Lean — Ceremonias

- Reuniones de mejora continua
- Eventos Kaizen para solucionar cuellos de botella`,
          'Artefactos': `Lean — Artefactos

- Mapa de flujo de valor
- Kanban/visual boards
- Definición de valor para el cliente`,
          'Métricas': `Lean — Métricas

- Tiempo de ciclo
- Porcentaje de valor entregado
- Nivel de inventario en proceso`,
          'Cuándo usar': `Lean — Cuándo usarlo

- Organizaciones que buscan eficiencia y rápido aprendizaje
- Procesos con desperdicio evidente`,
          'Cuándo evitar': `Lean — Cuándo evitarlo

- Contextos donde la reducción de trabajo en curso puede afectar disponibilidad crítica`,
          'Ventajas': `Lean — Ventajas

- Menos desperdicio
- Mayor velocidad de entrega
- Mejora continua de procesos`,
          'Desventajas': `Lean — Desventajas

- Requiere cultura de mejora continua
- Puede ser complejo en organizaciones grandes sin apoyo`,
          'Ejemplos prácticos': `Lean — Ejemplos prácticos

- Reducción de pasos en un proceso de aprobación
- Implementación de tablero visual para reducir inventario en proceso`,
        },
        SAFe: {
          '¿Qué es?': `SAFe — ¿qué es?

Framework para escalar prácticas ágiles en grandes organizaciones, coordinando múltiples equipos, programas y soluciones.`,
          'Roles típicos': `SAFe — Roles típicos

- Release Train Engineer (RTE)
- Product Management
- System Architect
- Equipos ágiles y stakeholders a nivel de programa.`,
          'Prácticas clave': `SAFe — Prácticas clave

- Planificación de PI (Program Increment)
- Sincronización entre equipos
- Arquitectura emergente
- Gestión de portfolio ágil`,
          'Fases': `SAFe — Fases

- Planificación de PI
- Iteraciones por equipo
- System Demo
- Inspect & Adapt`,
          'Ceremonias': `SAFe — Ceremonias

- PI Planning
- System demo
- Scrum of scrums y sincronizaciones de program`,
          'Artefactos': `SAFe — Artefactos

- Backlogs a nivel team/program/portfolio
- PI objectives
- Roadmaps`,
          'Métricas': `SAFe — Métricas

- Cumplimiento de PI objectives
- Predictability
- Flow metrics a nivel solución`,
          'Cuándo usar': `SAFe — Cuándo usarlo

- Organizaciones grandes que requieren coordinación entre muchos equipos y alineación estratégica`,
          'Cuándo evitar': `SAFe — Cuándo evitarlo

- Organizaciones pequeñas donde el overhead de coordinación sería excesivo`,
          'Ventajas': `SAFe — Ventajas

- Alineación a gran escala
- Gobernanza y planificación coordinada`,
          'Desventajas': `SAFe — Desventajas

- Complejidad y overhead
- Requiere inversión en cambio organizacional`,
          'Ejemplos prácticos': `SAFe — Ejemplos prácticos

- Empresas con varios ARTs (Agile Release Trains) que planifican por PI cada 8-12 semanas`,
        },
        Scrumban: {
          '¿Qué es?': `Scrumban — ¿qué es?

Híbrido entre Scrum y Kanban que combina sprints ligeros con límites de WIP para equipos que necesitan estructura y flexibilidad.`,
          'Roles típicos': `Scrumban — Roles típicos

- Roles similares a Scrum pero con mayor flexibilidad; el equipo adapta prácticas según necesidad.`,
          'Prácticas clave': `Scrumban — Prácticas clave

- Uso de tablero Kanban con sprints cuando convenga
- Límites WIP
- Revisión periódica y mejora continua`,
          'Fases': `Scrumban — Fases

- Planificación ligera
- Flujo continuo de trabajo con ventanas de entrega`,
          'Ceremonias': `Scrumban — Ceremonias

- Standups diarios
- Revisión y retro periódicas
- Planning ligero según necesidad`,
          'Artefactos': `Scrumban — Artefactos

- Tablero híbrido
- Backlog priorizado`,
          'Métricas': `Scrumban — Métricas

- Lead time
- Throughput
- Cumplimiento de compromisos por iteración`,
          'Cuándo usar': `Scrumban — Cuándo usarlo

- Equipos que migran de Scrum a Kanban o necesitan ambos enfoques`,
          'Cuándo evitar': `Scrumban — Cuándo evitarlo

- Cuando se necesita estructura rígida de entrega o sincronización estricta entre muchos equipos`,
          'Ventajas': `Scrumban — Ventajas

- Flexibilidad y estructura balanceadas
- Menor overhead que Scrum puro`,
          'Desventajas': `Scrumban — Desventajas

- Requiere decidir y mantener políticas claras
- Puede quedar en ambigüedad si no se define bien`,
          'Ejemplos prácticos': `Scrumban — Ejemplos prácticos

- Equipos que mantienen sprints mensuales pero gestionan tarjetas de mantenimiento con Kanban`,
        },
        Crystal: {
          '¿Qué es?': `Crystal — ¿qué es?

Familia de metodologías adaptables según tamaño y criticidad del equipo; enfatiza personas y comunicación.`,
          'Roles típicos': `Crystal — Roles típicos

- Roles flexibles; se adapta según el tamaño del equipo y la criticidad del proyecto.`,
          'Prácticas clave': `Crystal — Prácticas clave

- Comunicación cercana
- Entrega frecuente
- Adaptación de prácticas según contexto`,
          'Fases': `Crystal — Fases

- Iteraciones cortas
- Entregas incrementales
- Ajustes según retroalimentación`,
          'Ceremonias': `Crystal — Ceremonias

- Reuniones de coordinación y retrospectivas adaptadas al equipo`,
          'Artefactos': `Crystal — Artefactos

- Historias o items priorizados
- Documentación mínima necesaria`,
          'Métricas': `Crystal — Métricas

- Ritmo de entregas
- Calidad percibida por stakeholders`,
          'Cuándo usar': `Crystal — Cuándo usarlo

- Equipos pequeños o proyectos con necesidad de adaptabilidad y comunicación directa`,
          'Cuándo evitar': `Crystal — Cuándo evitarlo

- Proyectos que requieren procesos muy rígidos o regulaciones estrictas sin margen de adaptación`,
          'Ventajas': `Crystal — Ventajas

- Adaptabilidad
- Enfoque en personas y comunicación`,
          'Desventajas': `Crystal — Desventajas

- Poca guía prescriptiva; depende mucho de la experiencia del equipo`,
          'Ejemplos prácticos': `Crystal — Ejemplos prácticos

- Equipos pequeños que ajustan prácticas según aprendizaje`,
        },
        FDD: {
          '¿Qué es?': `FDD — ¿qué es?

Feature-Driven Development: enfoque orientado a entregar funcionalidades bien definidas, con modelado y planificación por features.`,
          'Roles típicos': `FDD — Roles típicos

- Chief Architect, Feature Owner, Developers; enfoque en roles para modelado y entrega de features.`,
          'Prácticas clave': `FDD — Prácticas clave

- Modelado por dominios
- Planificación y diseño por features
- Entrega incremental de funcionalidades`,
          'Fases': `FDD — Fases

- Desarrollo de un modelo general
- Construcción de lista de features
- Planificación por features
- Diseño e implementación por feature`,
          'Ceremonias': `FDD — Ceremonias

- Reuniones de planificación por feature
- Revisiones de diseño y entrega`,
          'Artefactos': `FDD — Artefactos

- Lista de features
- Diseños y modelos de dominio
- Incrementos de código por feature`,
          'Métricas': `FDD — Métricas

- Número de features completadas
- Tiempo por feature
- Calidad de entrega por feature`,
          'Cuándo usar': `FDD — Cuándo usarlo

- Proyectos con muchas funcionalidades claramente definibles y necesidad de progreso medible por feature`,
          'Cuándo evitar': `FDD — Cuándo evitarlo

- Proyectos muy exploratorios donde las features no se pueden definir con antelación`,
          'Ventajas': `FDD — Ventajas

- Claridad en entregables
- Buen seguimiento del progreso por features`,
          'Desventajas': `FDD — Desventajas

- Menos flexible si las features cambian mucho
- Puede requerir más diseño inicial`,
          'Ejemplos prácticos': `FDD — Ejemplos prácticos

- Proyectos grandes con catálogo de funcionalidades que pueden planificarse y entregarse por partes`,
        }
      }

  // Iniciar modo aprendizaje con metodología y tema específico
  const startLearningWithTopic = async (methodology, topic) => {
    setLoading(true)
    try {
      // Construir la pregunta tal como se haría originalmente
      const question = topic.question.replace('{method}', methodology)

      // Buscar contenido estático en el objeto local
      const methodContent = staticContent[methodology] || staticContent[methodology.replace(/\s*\(.*\)$/, '')] || {}
      let responseContent = methodContent[topic.name]

      if (!responseContent) {
        responseContent = `No hay contenido estático preparado para "${topic.name}" en ${methodology}.`
      }

      // Normalizar y limpiar
      responseContent = responseContent.replace(/\\n/g, '\n').trim()

      const userMsg = { role: 'user', content: question, ts: new Date().toISOString() }
      const assistantMsg = { role: 'assistant', content: responseContent, ts: new Date().toISOString() }

      setMessages([userMsg, assistantMsg])
      setTrainingActive(true)
    } catch (e) {
      console.error('start learning error', e)
      const errorContent = e?.message || 'Error al cargar la información. Intenta de nuevo.'
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
                              // Detectar si el texto ya contiene un emoji
                              const hasEmoji = /[\u{1F300}-\u{1F9FF}]|[\u{2600}-\u{26FF}]|[\u{2700}-\u{27BF}]/u.test(trimmed)
                              
                              return (
                                <div key={idx} className="mt-6 mb-3">
                                  <h4 className="text-lg font-semibold text-blue-800 flex items-center gap-2">
                                    {!hasEmoji && <span className="text-xl">💡</span>}
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
