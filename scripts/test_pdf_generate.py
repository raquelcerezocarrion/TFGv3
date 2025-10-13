from backend.app import render_chat_report_inline

# mensajes mínimos que permitirán crear un DAFO (fuerza, debilidad, oportunidad, amenaza)
msgs = [
    {"role": "assistant", "content": "Fortalezas: equipo con experiencia.\nDebilidades: falta de presupuesto.\nOportunidades: nicho en crecimiento.\nAmenazas: competidores consolidados."},
]

report_meta = {
    "project": "Proyecto Ejemplo",
    "client": "Cliente X",
    "author": "Asistente",
    "session_id": "s123",
    # probar con metodología 'Scrum'
    "metodologia": "Scrum",
    # fases en el formato que puede parsear el generador
    "fases": "Discovery 2s • Iteraciones 6s • Hardening 2s • Release 1s",
    # detalles por fase para el diagrama
    "phase_contents": {
        "Discovery": ["Determinación de los objetivos", "Definición de los involucrados", "Presentación del equipo"],
        "Iteraciones": ["Desarrollo iterativo", "TDD / Refactor", "Integración continua"],
        "Hardening": ["Pruebas de aceptación", "Correcciones finales"],
        "Release": ["Entrega final", "Handover / Documentación"],
    }
}

pdf = render_chat_report_inline(msgs, title="Prueba PDF con DAFO y metodología", report_meta=report_meta)
open('test_chat_method.pdf', 'wb').write(pdf)
print('test_chat_method.pdf generado')
