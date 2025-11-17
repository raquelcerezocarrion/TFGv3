"""Test que simula generar propuesta via brain directamente.

Uso:
    python -c "import sys; sys.path.insert(0, '.'); exec(open('scripts/test_brain_proposal.py').read())"
"""
from backend.engine.brain import generate_reply
from backend.memory.state_store import SessionLocal, ProposalLog

session_id = "test-brain-direct-456"
text = "Necesito una app de ecommerce con catálogo, carrito y pagos"

print(f"Llamando a generate_reply con: '{text}'")
response, debug = generate_reply(session_id, text)
print(f"\nRespuesta ({len(response)} chars):")
print(response[:300])
print(f"\nDebug: {debug}")

# Verificar si se guardó
print(f"\n Buscando propuestas con session_id = '{session_id}'...")
with SessionLocal() as db:
    rows = db.query(ProposalLog).filter(ProposalLog.session_id == session_id).all()
    print(f"✅ Encontradas {len(rows)} propuestas")
    for r in rows:
        print(f"   - ID: {r.id}, Metodología: {r.proposal_json.get('methodology')}")
