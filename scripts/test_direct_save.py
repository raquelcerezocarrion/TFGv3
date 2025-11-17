import sys
sys.path.insert(0, '.')
from backend.memory.state_store import save_proposal
from backend.engine.planner import generate_proposal

p = generate_proposal('app bancaria con seguridad')
print(f"Propuesta generada: {p.get('methodology')}")
pid = save_proposal('test-direct-final', 'app bancaria con seguridad', p)
print(f"Guardada con ID: {pid}")
