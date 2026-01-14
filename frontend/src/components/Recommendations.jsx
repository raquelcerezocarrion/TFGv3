import React, { useState } from 'react'
import axios from 'axios'
import { API_BASE } from '../api'

export default function Recommendations({ token }) {
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [recommendation, setRecommendation] = useState(null)
  const [error, setError] = useState(null)

  const base = API_BASE

  const search = async () => {
    const q = query.trim()
    if (!q) return
    setLoading(true); setError(null)
    try {
      const { data } = await axios.post(`${base}/projects/recommend`, { query: q }, { headers: { 'Content-Type': 'application/json' } })
      setRecommendation(data)
    } catch (e) {
      setError(e?.response?.data?.detail || e.message)
    } finally { setLoading(false) }
  }

  return (
    <div className="h-full flex flex-col gap-4">
      <div className="rounded-2xl p-4 bg-white/70 backdrop-blur border shadow-sm">
        <h2 className="text-lg font-semibold mb-2">Recomendaciones</h2>
        <p className="text-sm text-gray-600 mb-3">Describe el proyecto que quieres hacer y te mostraré qué metodología se suele usar, roles de equipo típicos y otras características habituales en proyectos similares.</p>

        <div className="flex gap-2">
          <textarea
            className="flex-1 border rounded-xl px-3 py-2 min-h-[90px]"
            placeholder="Ej: app de seguros con gestión de pólizas y reclamaciones online"
            value={query}
            onChange={(e)=>setQuery(e.target.value)}
          />
          <div className="flex flex-col gap-2">
            <button className="px-4 py-2 rounded-xl bg-emerald-600 text-white disabled:opacity-50" onClick={search} disabled={loading}>Buscar</button>
            <button className="px-4 py-2 rounded-xl border" onClick={()=>{ setQuery(''); setRecommendation(null); setError(null) }}>Limpiar</button>
          </div>
        </div>
        {error && <div className="mt-2 text-sm text-red-600">{String(error)}</div>}
      </div>

      <div className="flex-1 overflow-y-auto pr-1 custom-scroll">
        {loading && <div className="text-sm text-gray-500">Analizando tu proyecto…</div>}
        {!loading && !recommendation && <div className="text-sm text-gray-500">No hay resultados todavía. Escribe una descripción de tu proyecto y pulsa Buscar.</div>}
        
        {recommendation && (
          <div className="space-y-4">
            {/* Metodología */}
            <div className="rounded-xl bg-white/70 backdrop-blur border shadow-sm p-4">
              <h3 className="text-base font-semibold mb-2 flex items-center gap-2">
                <span className="text-xl">📋</span> Metodología Recomendada
              </h3>
              <div className="mb-2">
                <span className="inline-block px-3 py-1 bg-emerald-100 text-emerald-700 rounded-lg font-medium">
                  {recommendation.methodology.name}
                </span>
              </div>
              <p className="text-sm text-gray-700 mb-3">{recommendation.methodology.description}</p>
              
              {recommendation.methodology.best_for && recommendation.methodology.best_for.length > 0 && (
                <div className="mb-2">
                  <p className="text-xs font-medium text-gray-600 mb-1">✅ Ideal para:</p>
                  <ul className="text-xs text-gray-700 space-y-1">
                    {recommendation.methodology.best_for.map((item, i) => (
                      <li key={i} className="pl-3">• {item}</li>
                    ))}
                  </ul>
                </div>
              )}

              {recommendation.methodology.reasons && recommendation.methodology.reasons.length > 0 && (
                <div className="mt-2 pt-2 border-t">
                  <p className="text-xs font-medium text-gray-600 mb-1">💡 Por qué en tu caso:</p>
                  <ul className="text-xs text-gray-700 space-y-1">
                    {recommendation.methodology.reasons.map((reason, i) => (
                      <li key={i} className="pl-3">• {reason}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            {/* Roles de Equipo */}
            {recommendation.typical_roles && recommendation.typical_roles.length > 0 && (
              <div className="rounded-xl bg-white/70 backdrop-blur border shadow-sm p-4">
                <h3 className="text-base font-semibold mb-3 flex items-center gap-2">
                  <span className="text-xl">👥</span> Roles de Equipo Típicos
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {recommendation.typical_roles.map((role, i) => (
                    <div key={i} className="bg-blue-50 rounded-lg p-3">
                      <p className="text-sm font-medium text-blue-900">{role.name}</p>
                      <p className="text-xs text-blue-700 mt-1">{role.description}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Fases Típicas */}
            {recommendation.typical_phases && recommendation.typical_phases.length > 0 && (
              <div className="rounded-xl bg-white/70 backdrop-blur border shadow-sm p-4">
                <h3 className="text-base font-semibold mb-3 flex items-center gap-2">
                  <span className="text-xl">🚀</span> Fases Habituales del Proyecto
                </h3>
                <div className="space-y-2">
                  {recommendation.typical_phases.map((phase, i) => (
                    <div key={i} className="border-l-4 border-purple-400 pl-3 py-2">
                      <div className="flex items-baseline justify-between">
                        <p className="text-sm font-medium text-gray-900">{phase.name}</p>
                        {phase.duration && (
                          <span className="text-xs text-purple-600 font-medium">{phase.duration}</span>
                        )}
                      </div>
                      <p className="text-xs text-gray-600 mt-1">{phase.description}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Prácticas Clave */}
            {recommendation.key_practices && recommendation.key_practices.length > 0 && (
              <div className="rounded-xl bg-white/70 backdrop-blur border shadow-sm p-4">
                <h3 className="text-base font-semibold mb-3 flex items-center gap-2">
                  <span className="text-xl">⚡</span> Prácticas Clave
                </h3>
                <div className="flex flex-wrap gap-2">
                  {recommendation.key_practices.map((practice, i) => (
                    <span key={i} className="px-3 py-1 bg-yellow-100 text-yellow-800 rounded-full text-xs font-medium">
                      {practice}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Consideraciones Importantes */}
            {recommendation.important_considerations && recommendation.important_considerations.length > 0 && (
              <div className="rounded-xl bg-white/70 backdrop-blur border shadow-sm p-4">
                <h3 className="text-base font-semibold mb-3 flex items-center gap-2">
                  <span className="text-xl">⚠️</span> Consideraciones Importantes
                </h3>
                <ul className="space-y-2">
                  {recommendation.important_considerations.map((consideration, i) => (
                    <li key={i} className="text-sm text-gray-700 flex items-start gap-2">
                      <span className="text-orange-500 font-bold mt-0.5">•</span>
                      <span>{consideration}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
