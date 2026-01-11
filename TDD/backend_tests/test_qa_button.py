"""Test específico para verificar que el botón QA funciona correctamente."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.engine.brain import generate_reply, set_last_proposal, get_last_proposal

session_id = "test_qa_button_unique_123"

# Crear una propuesta inicial simple
initial_proposal = {
    "methodology": "Scrum",
    "duration_weeks": 12,
    "team": [
        {"role": "PM", "count": 1.0},
        {"role": "Backend Dev", "count": 2.0},
        {"role": "QA", "count": 1.0}
    ],
    "budget": {"total_eur": 50000},
    "phases": [{"name": "Sprint 1", "weeks": 2}]
}

# Guardar propuesta inicial
set_last_proposal(session_id, initial_proposal, "proyecto web simple")

print("=" * 70)
print("TEST: Cambiar QA de x1 a x2")
print("=" * 70)

print(f"\n1. Propuesta inicial:")
for member in initial_proposal["team"]:
    print(f"   - {member['role']}: {member['count']}")

# Simular el comando que envía el frontend cuando usuario hace clic en QA y luego x2
command = "/cambiar: QA x2"
print(f"\n2. Enviando comando: {repr(command)}")

# Llamar a generate_reply (session_id PRIMERO, message SEGUNDO)
response, tag = generate_reply(session_id, command)

print(f"\n3. Respuesta del backend:")
print(f"   Tag: {tag}")
print(f"   Response preview: {response[:200]}...")

# Verificar que la propuesta se actualizó
updated_data = get_last_proposal(session_id)

print(f"\n4. Propuesta actualizada:")
if updated_data and len(updated_data) == 2:
    updated_proposal = updated_data[0]  # get_last_proposal retorna (proposal, req_text)
    if updated_proposal:
        for member in updated_proposal["team"]:
            print(f"   - {member['role']}: {member['count']}")
        
        # Verificar que QA cambió a 2.0
        qa_member = next((m for m in updated_proposal["team"] if m["role"] == "QA"), None)
        if qa_member:
            if qa_member["count"] == 2.0:
                print(f"\n✅ TEST PASSED: QA cambió correctamente de 1.0 a 2.0")
            else:
                print(f"\n❌ TEST FAILED: QA debería ser 2.0 pero es {qa_member['count']}")
        else:
            print(f"\n❌ TEST FAILED: No se encontró el rol QA en el equipo")
    else:
        print(f"\n❌ TEST FAILED: No hay propuesta actualizada")
else:
    print(f"\n❌ TEST FAILED: get_last_proposal no retornó datos válidos")
