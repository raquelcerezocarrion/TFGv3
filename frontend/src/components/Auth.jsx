import React, { useState } from 'react'
import axios from 'axios'

export default function Auth({ onLogin }){
  const [mode, setMode] = useState('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [info, setInfo] = useState(null)

  const apiBase = `http://${window.location.hostname}:8000`

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
    <div className="p-4">
      <h2 className="text-xl font-bold mb-2">{mode === 'login' ? 'Iniciar sesión' : 'Registro'}</h2>
      {error && <div className="text-red-600 mb-2">{error}</div>}
      {info && <div className="text-green-600 mb-2">{info}</div>}
      {mode === 'register' && (
        <input className="w-full border rounded px-2 py-1 mb-2" placeholder="Nombre completo" value={name} onChange={e=>setName(e.target.value)} />
      )}
      <input className="w-full border rounded px-2 py-1 mb-2" placeholder="Email" value={email} onChange={(e)=>{ setEmail(e.target.value); setError(null); setInfo(null) }} />
      <input type="password" className="w-full border rounded px-2 py-1 mb-2" placeholder="Contraseña" value={password} onChange={(e)=>{ setPassword(e.target.value); setError(null); setInfo(null) }} />
      <div className="flex gap-2">
        <button className="px-4 py-2 bg-blue-600 text-white rounded" onClick={submit} disabled={loading}>{loading ? 'Enviando…' : (mode === 'login' ? 'Entrar' : 'Registrar')}</button>
        <button className="px-4 py-2 border rounded" onClick={()=>{ setMode(mode==='login'?'register':'login'); setError(null); setInfo(null) }}>{mode==='login'?'Crear cuenta':'Tengo cuenta'}</button>
      </div>

      <div className="text-xs text-gray-500 mt-2">
        Nota: para conveniencia esta demo guarda email y contraseña en el navegador (localStorage). En producción no es seguro almacenar contraseñas en texto claro; considera usar "recordarme" sin guardar la contraseña, o cookies seguras.
      </div>
    </div>
  )
}
