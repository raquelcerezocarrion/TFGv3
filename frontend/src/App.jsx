import React from 'react'
import Chat from './components/Chat.jsx'

export default function App() {
  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="w-full max-w-3xl bg-white shadow-lg rounded-2xl p-4">
        <header className="mb-2">
          <h1 className="text-2xl font-bold">TFG Consultoría Assistant — Parte 1</h1>
          <p className="text-sm text-gray-500">Chat funcional (eco) + propuesta dummy</p>
        </header>
        <Chat />
      </div>
    </div>
  )
}
