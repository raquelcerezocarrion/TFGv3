from backend.engine.brain import generate_reply

print("╔═════════════════════════════════════════════════════════════════════════════════╗")
print("║          PRUEBA DE FLUJO CON EMPLEADOS GUARDADOS                               ║")
print("╚═════════════════════════════════════════════════════════════════════════════════╝\n")

session = "test_employee_flow"

# Paso 1: Generar una propuesta
print("="*85)
print("PASO 1: Generar propuesta")
print("="*85)
r1 = generate_reply(session, "app bancaria con transferencias")
print(f"Usuario: app bancaria con transferencias")
print(f"Asistente: {r1[0][:200]}...")
print(f"Estado: {r1[1]}\n")

# Paso 2: Aceptar la propuesta
print("="*85)
print("PASO 2: Aceptar propuesta")
print("="*85)
r2 = generate_reply(session, "acepto la propuesta")
print(f"Usuario: acepto la propuesta")
print(f"Asistente:\n{r2[0]}")
print(f"Estado: {r2[1]}\n")

# Paso 3a: Elegir usar empleados guardados
print("="*85)
print("PASO 3a: Elegir usar empleados guardados")
print("="*85)
r3a = generate_reply(session, "usar empleados guardados")
print(f"Usuario: usar empleados guardados")
print(f"Asistente:\n{r3a[0]}")
print(f"Estado: {r3a[1]}\n")

# Paso 4a: Enviar datos JSON de empleados
print("="*85)
print("PASO 4a: Enviar JSON de empleados")
print("="*85)
employees_json = '''[
  {"name": "Ana Ruiz", "role": "Backend Dev", "skills": "Python, Django, AWS", "seniority": "Senior", "availability_pct": 100},
  {"name": "Luis Pérez", "role": "QA", "skills": "Cypress, E2E, Selenium", "seniority": "Semi Senior", "availability_pct": 50},
  {"name": "María García", "role": "Frontend Dev", "skills": "React, TypeScript, CSS", "seniority": "Senior", "availability_pct": 80},
  {"name": "Carlos López", "role": "Backend Dev", "skills": "Python, FastAPI, PostgreSQL", "seniority": "Mid", "availability_pct": 100}
]'''

r4a = generate_reply(session, employees_json)
print(f"Usuario: [JSON con 4 empleados]")
print(f"Asistente:\n{r4a[0][:500]}...")
print(f"Estado: {r4a[1]}\n")

print("\n" + "="*85)
print("FLUJO ALTERNATIVO: Introducir plantilla manualmente")
print("="*85)

# Nuevo flujo con sesión diferente
session2 = "test_manual_flow"

# Generar propuesta
r1b = generate_reply(session2, "sistema de soporte 24/7")
print(f"\nUsuario: sistema de soporte 24/7")
print(f"Asistente: {r1b[0][:150]}...")

# Aceptar propuesta
r2b = generate_reply(session2, "acepto")
print(f"\nUsuario: acepto")
print(f"Asistente:\n{r2b[0][:300]}...")

# Elegir manual
r3b = generate_reply(session2, "manual")
print(f"\nUsuario: manual")
print(f"Asistente:\n{r3b[0]}")
print(f"Estado: {r3b[1]}")
