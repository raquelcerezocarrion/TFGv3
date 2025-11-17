"""Test directo de save_proposal para verificar que funciona.

Uso:
    python scripts/test_proposal_save.py
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from backend.memory.state_store import save_proposal, SessionLocal, ProposalLog

# Test simple
session_id = "test-save-proposal-123"
requirements = "App de test con funcionalidad X"
proposal = {
    "methodology": "Scrum",
    "team": [],
    "phases": [{"name": "Sprint 1"}],
    "budget": {"total_eur": 10000}
}

print("Guardando propuesta...")
proposal_id = save_proposal(session_id, requirements, proposal)
print(f"✅ Propuesta guardada con ID: {proposal_id}")

# Verificar que se guardó
print("\nVerificando en base de datos...")
with SessionLocal() as db:
    row = db.query(ProposalLog).filter(ProposalLog.id == proposal_id).first()
    if row:
        print(f"✅ Propuesta encontrada:")
        print(f"   ID: {row.id}")
        print(f"   Session ID: {row.session_id}")
        print(f"   Requirements: {row.requirements}")
        print(f"   Metodología: {row.proposal_json.get('methodology')}")
    else:
        print(f"❌ No se encontró la propuesta con ID {proposal_id}")

# Buscar por session_id con patrón LIKE
print("\nBuscando propuestas con session_id LIKE 'test-save-%'...")
with SessionLocal() as db:
    rows = db.query(ProposalLog).filter(ProposalLog.session_id.like('test-save-%')).all()
    print(f"✅ Encontradas {len(rows)} propuestas")
    for r in rows:
        print(f"   - ID: {r.id}, Session: {r.session_id}")
