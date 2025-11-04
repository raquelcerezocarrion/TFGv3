import React, { useState } from 'react'
import axios from 'axios'

export default function Recommendations({ token }) {
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [items, setItems] = useState([])
  const [error, setError] = useState(null)

  const base = `http://${window.location.hostname}:8000`

  const search = async () => {
    const q = query.trim()
    if (!q) return
    setLoading(true); setError(null)
    try {
      const { data } = await axios.post(`${base}/projects/recommend`, { query: q, top_k: 5 }, { headers: { 'Content-Type': 'application/json' } })
      setItems(data || [])
    } catch (e) {
      setError(e?.response?.data?.detail || e.message)
    } finally { setLoading(false) }
  }

  return (
    <div className="h-full flex flex-col gap-4">
      <div className="rounded-2xl p-4 bg-white/70 backdrop-blur border shadow-sm">
        <h2 className="text-lg font-semibold mb-2">Recomendaciones</h2>
        <p className="text-sm text-gray-600 mb-3">Describe el proyecto que quieres hacer y te sugeriré proyectos parecidos como inspiración. Puedes consultar sus PDF finales.</p>

        <div className="flex gap-2">
          <textarea
            className="flex-1 border rounded-xl px-3 py-2 min-h-[90px]"
            placeholder="Ej: App de reservas con pagos en Stripe y panel de administración para restaurantes"
            value={query}
            onChange={(e)=>setQuery(e.target.value)}
          />
          <div className="flex flex-col gap-2">
            <button className="px-4 py-2 rounded-xl bg-emerald-600 text-white disabled:opacity-50" onClick={search} disabled={loading}>Buscar</button>
            <button className="px-4 py-2 rounded-xl border" onClick={()=>{ setQuery(''); setItems([]); setError(null) }}>Limpiar</button>
          </div>
        </div>
        {error && <div className="mt-2 text-sm text-red-600">{String(error)}</div>}
      </div>

      <div className="flex-1 overflow-y-auto pr-1 custom-scroll">
        {loading && <div className="text-sm text-gray-500">Buscando proyectos similares…</div>}
        {!loading && items.length === 0 && <div className="text-sm text-gray-500">No hay resultados todavía. Escribe una descripción y pulsa Buscar.</div>}
        <ul className="space-y-3">
          {items.map((it)=>{
            const pdf = token ? `${base}${it.pdf_url}?token=${encodeURIComponent(token)}` : `${base}${it.pdf_url}`
            return (
              <li key={it.id} className="rounded-xl bg-white/70 backdrop-blur border shadow-sm p-3">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="font-medium">{it.methodology ? `${it.methodology}` : 'Proyecto anterior'}</div>
                    <div className="text-xs text-gray-500">Similitud: {(it.similarity*100).toFixed(0)}%</div>
                  </div>
                  <div className="flex items-center gap-2">
                    <a className="px-3 py-2 rounded-xl bg-blue-600 text-white hover:opacity-90" href={pdf} target="_blank" rel="noreferrer">Ver PDF</a>
                  </div>
                </div>
                <div className="mt-2 text-sm text-gray-700 line-clamp-3"><span className="text-gray-500">Requisitos: </span>{it.requirements}</div>
                {it.phases && it.phases.length>0 && (
                  <div className="mt-2 text-xs text-gray-600">
                    Fases: {it.phases.map(p=>`${p.name} (${p.weeks}w)`).join(' → ')}
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      </div>
    </div>
  )
}
