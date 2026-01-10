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
      className={`px-3 py-2 rounded-xl border-2 transition font-medium ${current === key ? 'bg-white text-blue-700 border-white shadow-md' : 'bg-white/10 text-white border-white/20 hover:bg-white/20'}`}
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
        <button className="ml-2 text-sm text-white font-medium hover:text-white/80 transition" onClick={onLogout}>Cerrar sesión</button>
      )}
    </nav>
  )
}
