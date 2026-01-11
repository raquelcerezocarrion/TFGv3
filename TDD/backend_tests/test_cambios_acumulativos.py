"""
Test para verificar que los cambios en la propuesta son acumulativos.
Ejemplo: XP → Kanban → PM x2 debe resultar en Kanban con PM x2
"""
from backend.engine.brain import generate_reply, get_last_proposal
import uuid

def test_cambios_acumulativos():
    session_id = f"test_{uuid.uuid4().hex[:8]}"
    
    # 1. Generar propuesta inicial con XP
    text1, _ = generate_reply(session_id, "/propuesta: Sistema de gestión con metodología ágil")
    print("\n1. Propuesta inicial:")
    print(text1[:200])
    
    proposal1, _ = get_last_proposal(session_id)
    assert proposal1 is not None
    metodo_inicial = proposal1.get("methodology")
    print(f"Metodología inicial: {metodo_inicial}")
    
    # 2. Cambiar a Kanban
    text2, _ = generate_reply(session_id, "/cambiar: Kanban")
    print("\n2. Después de cambiar a Kanban:")
    print(text2[:200])
    
    proposal2, _ = get_last_proposal(session_id)
    assert proposal2 is not None
    assert proposal2.get("methodology") == "Kanban", f"Esperaba Kanban, obtuve {proposal2.get('methodology')}"
    print(f"✓ Metodología cambiada a: {proposal2.get('methodology')}")
    
    # 3. Cambiar PM a x2
    text3, _ = generate_reply(session_id, "/cambiar: PM x2")
    print("\n3. Después de cambiar PM a x2:")
    print(text3[:200])
    
    proposal3, _ = get_last_proposal(session_id)
    assert proposal3 is not None
    
    # Verificar que la metodología sigue siendo Kanban
    metodo_final = proposal3.get("methodology")
    print(f"Metodología final: {metodo_final}")
    assert metodo_final == "Kanban", f"❌ ERROR: Esperaba Kanban, obtuve {metodo_final}"
    
    # Verificar que PM está en x2
    team = proposal3.get("team", [])
    pm_role = next((r for r in team if "PM" in r.get("role", "")), None)
    assert pm_role is not None, "No se encontró el rol PM"
    pm_count = pm_role.get("count")
    print(f"PM count: {pm_count}")
    assert pm_count == 2.0, f"❌ ERROR: Esperaba PM x2, obtuve PM x{pm_count}"
    
    print(f"\n✅ TEST PASADO: Metodología = {metodo_final}, PM = x{pm_count}")
    print("Los cambios son acumulativos correctamente!")

if __name__ == "__main__":
    test_cambios_acumulativos()
