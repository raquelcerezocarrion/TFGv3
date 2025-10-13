from backend.app import render_chat_report_inline

# Mensaje con formato similar al screenshot (incluye emojis y 'Metodología: XP')
msgs = [
    {"role": "assistant", "content": "📌 Metodología: XP\n👥 Equipo: PM x0.5, Tech Lead x0.5, Backend Dev x2, Frontend Dev x1, QA x1, UX/UI x0.5, Backend Dev x0.5\n🧩 Fases: Discovery + Historias & CRC (2s) → Iteraciones con TDD/Refactor/CI (6s) → Hardening & Pruebas de Aceptación (2s) → Release & Handover (1s)\n💶 Presupuesto: 78.045,00 € (incluye 10% contingencia)\n⚠️ Riesgos: Cambios de alcance sin prioridad clara; Dependencias externas (APIs/terceros); Datos insuficientes para pruebas de rendimiento/escalado; PCI-DSS, fraude/chargebacks, idempotencia en cobros; Aprobación en tiendas y compatibilidad de dispositivos"},
]

pdf = render_chat_report_inline(msgs, title="Prueba XP -> PDF")
open('test_xp.pdf', 'wb').write(pdf)
print('test_xp.pdf generado')
