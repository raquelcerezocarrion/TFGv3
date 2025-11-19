from backend.engine.brain import generate_reply

print("╔═════════════════════════════════════════════════════════════════════════════════╗")
print("║          PRUEBA DE DETALLE DE PRESUPUESTO CON JUSTIFICACIÓN                   ║")
print("╚═════════════════════════════════════════════════════════════════════════════════╝\n")

casos = [
    ("app bancaria con transferencias y pagos", "FINTECH"),
    ("startup mvp red social", "STARTUP"),
    ("sistema de soporte 24/7", "SOPORTE"),
]

for query, label in casos:
    print(f"\n{'='*85}")
    print(f"🔍 CASO: {label} - '{query}'")
    print('='*85)
    
    # Primero generar la propuesta
    r1 = generate_reply(f's_{label}_1', query)
    print("✓ Propuesta generada\n")
    
    # Luego pedir el detalle del presupuesto
    r2 = generate_reply(f's_{label}_1', 'dame el detalle del presupuesto')
    
    if isinstance(r2, tuple):
        respuesta = r2[0]
    else:
        respuesta = r2
    
    print(respuesta)
    print("\n")
