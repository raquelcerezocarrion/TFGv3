from backend.engine.brain import generate_reply, _detect_new_proposal_intent
import logging
logging.basicConfig(level=logging.DEBUG)

text = 'startup mvp red social mascotas'
print("=== Prueba 1: detect_new_proposal_intent ===")
wants, flags = _detect_new_proposal_intent('s1', text)
print(f"wants_new_proposal: {wants}, flags: {flags}")

print("\n=== Prueba 2: generate_reply completo ===")
r = generate_reply('s1', text)
print(f"Respuesta: {r[0][:200]}...")
print(f"Label: {r[1]}")
