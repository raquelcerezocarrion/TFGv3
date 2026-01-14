import React, { useState } from 'react'
import axios from 'axios'
import { API_BASE } from '../api'

export default function Auth({ onLogin }){
  const [mode, setMode] = useState('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [info, setInfo] = useState(null)

  const apiBase = API_BASE

  // Load saved credentials if present
  React.useEffect(()=>{
    try{
      const raw = localStorage.getItem('tfg_creds')
      if(raw){
        const obj = JSON.parse(raw)
        if(obj.email) setEmail(obj.email)
        if(obj.password) setPassword(obj.password)
      }
    }catch(e){ /* ignore */ }
  }, [])

  const saveCreds = (emailVal, passwordVal) =>{
    try{
      localStorage.setItem('tfg_creds', JSON.stringify({ email: emailVal, password: passwordVal }))
    }catch(e){ /* ignore */ }
  }

  const submit = async () =>{
    setLoading(true); setError(null); setInfo(null)
    // Client-side validation to avoid 422 from backend
    if(!email || email.indexOf('@') === -1){
      setError('Email inválido. Introduce una dirección de correo válida.')
      setLoading(false)
      return
    }
    if(!password || password.length < 6){
      setError('La contraseña debe tener al menos 6 caracteres.')
      setLoading(false)
      return
    }
    try{
      if(mode === 'register'){
        const { data } = await axios.post(`${apiBase}/auth/register`, { email, password, full_name: name }, { headers: { 'Content-Type': 'application/json' } })
        // Save credentials locally
        saveCreds(email, password)
        // Auto-login: prefer token returned by register; if none, call login
        const token = data?.access_token
        if(token){
          onLogin(token)
        } else {
          // fallback: call login endpoint
          const res = await axios.post(`${apiBase}/auth/login`, { email, password }, { headers: { 'Content-Type': 'application/json' } })
          saveCreds(email, password)
          onLogin(res.data.access_token)
        }
      } else {
        const { data } = await axios.post(`${apiBase}/auth/login`, { email, password }, { headers: { 'Content-Type': 'application/json' } })
        // on successful login, save credentials and notify parent with token
        saveCreds(email, password)
        onLogin(data.access_token)
      }
    }catch(e){
      console.error('Auth error', e)
      // Prefer showing server-side validation details when present
      const srv = e?.response?.data
      if(srv){
        try{
          // FastAPI 422 returns { detail: [ ... ] }
          if(srv.detail) setError(JSON.stringify(srv.detail, null, 2))
          else setError(JSON.stringify(srv, null, 2))
        }catch(_){ setError(String(srv)) }
      } else {
        setError(e.message || 'Error de red')
      }
      // If register failed, attempt login as a fallback (useful if user already exists)
      if(mode === 'register'){
        try{
          // attempt login with same creds
          const r = await axios.post(`${apiBase}/auth/login`, { email, password }, { headers: { 'Content-Type': 'application/json' } })
          // if login succeeded, save and enter
          saveCreds(email, password)
          onLogin(r.data.access_token)
          return
        }catch(err){
          // if fallback login fails, switch to login view so user can try manually
          setMode('login')
          // if fallback returned an error with details, append it
          const srv2 = err?.response?.data
          if(srv2){
            try{ setError(prev => (prev ? prev + '\n' + JSON.stringify(srv2) : JSON.stringify(srv2))) }catch(_){ }
          }
        }
      }
    }finally{ setLoading(false) }
  }

  return (
    <div className="fixed inset-0 flex items-center justify-center overflow-hidden">
      {/* Fondo base con gradiente corporativo */}
      <div className="absolute inset-0 bg-gradient-to-br from-slate-800 via-blue-900 to-indigo-900"></div>
      
      {/* Patrón de cuadrícula sutil */}
      <div className="absolute inset-0" style={{
        backgroundImage: `
          linear-gradient(to right, rgba(255,255,255,0.03) 1px, transparent 1px),
          linear-gradient(to bottom, rgba(255,255,255,0.03) 1px, transparent 1px)
        `,
        backgroundSize: '40px 40px'
      }}></div>
      
      {/* Círculos decorativos sutiles */}
      <div className="absolute -top-40 -left-40 w-96 h-96 bg-blue-500/10 rounded-full blur-3xl"></div>
      <div className="absolute -bottom-40 -right-40 w-[600px] h-[600px] bg-indigo-500/10 rounded-full blur-3xl"></div>
      <div className="absolute top-1/3 -right-20 w-80 h-80 bg-slate-400/8 rounded-full blur-2xl"></div>
      <div className="absolute bottom-1/4 -left-20 w-72 h-72 bg-blue-400/8 rounded-full blur-2xl"></div>
      
      {/* Formas geométricas decorativas sutiles */}
      <div className="absolute top-20 left-1/4 w-32 h-32 border-2 border-white/10 rounded-lg rotate-12 backdrop-blur-sm"></div>
      <div className="absolute bottom-32 right-1/4 w-40 h-40 border-2 border-white/8 rounded-full backdrop-blur-sm"></div>
      <div className="absolute top-1/2 left-12 w-24 h-24 border-2 border-white/8 rounded-lg -rotate-12 backdrop-blur-sm"></div>
      
      <div className="w-full max-w-md relative z-10">
        <div className="bg-white/97 backdrop-blur-xl rounded-3xl shadow-2xl p-8 border border-blue-200/20">
          {/* Logo y título */}
          <div className="flex items-center justify-center mb-6">
            <div className="w-14 h-14 bg-gradient-to-br from-blue-600 to-indigo-700 rounded-2xl flex items-center justify-center text-white text-2xl shadow-xl mr-3">
              🎯
            </div>
            <div>
              <h2 className="text-2xl font-bold text-white drop-shadow-lg">
                {mode === 'login' ? 'Iniciar sesión' : 'Registro'}
              </h2>
            </div>
          </div>

          {/* Mensajes de error/info */}
          {error && (
            <div className="bg-red-50 border border-red-200 rounded-xl p-3 mb-4 flex items-start gap-2">
              <span className="text-red-600 text-lg">⚠️</span>
              <div className="text-red-700 text-sm flex-1">{error}</div>
            </div>
          )}
          {info && (
            <div className="bg-green-50 border border-green-200 rounded-xl p-3 mb-4 flex items-start gap-2">
              <span className="text-green-600 text-lg">✓</span>
              <div className="text-green-700 text-sm flex-1">{info}</div>
            </div>
          )}

          {/* Formulario */}
          <div className="space-y-4">
            {mode === 'register' && (
              <div>
                <label className="block text-sm font-medium text-white mb-1.5">Nombre completo</label>
                <input 
                  className="w-full border-2 border-gray-200 rounded-xl px-4 py-2.5 focus:border-blue-500 focus:outline-none transition" 
                  placeholder="Tu nombre" 
                  value={name} 
                  onChange={e=>setName(e.target.value)} 
                />
              </div>
            )}
            
            <div>
              <label className="block text-sm font-medium text-white mb-1.5">Email</label>
              <input 
                className="w-full border-2 border-gray-200 rounded-xl px-4 py-2.5 focus:border-blue-600 focus:ring-2 focus:ring-blue-100 focus:outline-none transition" 
                placeholder="tu@email.com" 
                value={email} 
                onChange={(e)=>{ setEmail(e.target.value); setError(null); setInfo(null) }} 
              />
            </div>
            
            <div>
              <label className="block text-sm font-medium text-white mb-1.5">Contraseña</label>
              <input 
                type="password" 
                className="w-full border-2 border-gray-200 rounded-xl px-4 py-2.5 focus:border-blue-600 focus:ring-2 focus:ring-blue-100 focus:outline-none transition" 
                placeholder="••••••" 
                value={password} 
                onChange={(e)=>{ setPassword(e.target.value); setError(null); setInfo(null) }} 
              />
            </div>
          </div>

          {/* Botones */}
          <div className="flex gap-3 mt-6">
            <button 
              className="flex-1 px-4 py-3 bg-gradient-to-r from-blue-600 to-indigo-700 text-white rounded-xl font-semibold hover:shadow-xl hover:from-blue-700 hover:to-indigo-800 transition-all disabled:opacity-50 disabled:cursor-not-allowed" 
              onClick={submit} 
              disabled={loading}
            >
              {loading ? '⏳ Enviando…' : (mode === 'login' ? 'Entrar' : 'Registrar')}
            </button>
            <button 
              className="px-4 py-3 bg-white border-2 border-blue-600 text-blue-700 rounded-xl font-semibold hover:bg-blue-50 transition" 
              onClick={()=>{ setMode(mode==='login'?'register':'login'); setError(null); setInfo(null) }}
            >
              {mode==='login'?'Crear cuenta':'Tengo cuenta'}
            </button>
          </div>

          {/* Nota de seguridad */}
          <div className="mt-6 text-xs text-gray-500 bg-gray-50 rounded-lg p-3 border border-gray-100">
            <span className="font-medium">Nota:</span> para conveniencia esta demo guarda email y contraseña en el navegador (localStorage). En producción no es seguro almacenar contraseñas en texto claro; considera usar "recordarme" sin guardar la contraseña, o cookies seguras.
          </div>
        </div>
      </div>
    </div>
  )
}
