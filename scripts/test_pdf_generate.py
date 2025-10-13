from backend.app import render_chat_report_inline

# mensajes mínimos que permitirán crear un DAFO (fuerza, debilidad, oportunidad, amenaza)
msgs = [
    {"role": "assistant", "content": "Fortalezas: equipo con experiencia.\nDebilidades: falta de presupuesto.\nOportunidades: nicho en crecimiento.\nAmenazas: competidores consolidados."},
]

pdf = render_chat_report_inline(msgs, title="Prueba PDF con DAFO")
open('test_chat.pdf', 'wb').write(pdf)
print('test_chat.pdf generado')
