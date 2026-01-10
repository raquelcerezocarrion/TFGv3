import React from 'react'

export default function TopNav({
  current = 'projects', // 'projects' | 'employees' | 'profile' | 'recommendations' | 'aprender'
  onGoProjects,
  onGoAprender,
  onGoRecommendations,
  onGoEmployees,
  onGoProfile,
  onLogout,
}) {
  const item = (key, label, onClick) => (
    <button
      className={`px-3 py-2 rounded-xl border transition ${current === key ? 'bg-gray-900 text-white border-gray-900' : 'hover:bg-gray-50'}`}
      onClick={() => {
        console.debug(`[TopNav] click ${label}`)
        try { onClick && onClick() } catch(e) { console.error('[TopNav] onClick error', e) }
      }}
    >
      {label}
    </button>
  )

  return (
    <nav className="flex items-center gap-2">
      {item('projects', 'Proyectos', onGoProjects)}
      {item('aprender', 'Aprender', onGoAprender)}
      {item('recommendations', 'Recomendaciones', onGoRecommendations)}
      {item('employees', 'Empleados', onGoEmployees)}
      {item('profile', 'Perfil', onGoProfile)}
      {onLogout && (
        <button className="ml-2 text-sm text-gray-600 hover:text-gray-800" onClick={onLogout}>Cerrar sesión</button>
      )}
    </nav>
  )
}
