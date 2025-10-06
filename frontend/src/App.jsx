import React from 'react'
import Chat from './components/Chat.jsx'
import Auth from './components/Auth.jsx'
import { useState } from 'react'

export default function App() {
  const [token, setToken] = useState(null)
  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="w-full max-w-3xl bg-white shadow-lg rounded-2xl p-4">
        <header className="mb-2">
          <h1 className="text-2xl font-bold">TFG Consultoría Assistant — Parte 1</h1>
          <p className="text-sm text-gray-500">Chat funcional (eco) + propuesta dummy</p>
        </header>
        {!token ? <Auth onLogin={(t)=>setToken(t)} /> : <Chat />}
      </div>
    </div>
  )
}
