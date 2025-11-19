from backend.engine.brain import generate_reply

print("\n🎯 COMPARACIÓN DETALLADA DE PRESUPUESTOS\n")

casos = [
    ("app bancaria con transferencias y pagos", "FINTECH"),
    ("startup mvp para red social", "STARTUP"),
    ("ERP enterprise para contabilidad y producción", "ERP"),
    ("sistema logístico para tracking", "LOGISTICS"),
]

for query, label in casos:
    print(f"\n{'='*80}")
    print(f"📋 {label}: {query}")
    print('='*80)
    
    r = generate_reply(f's_{label}', query)
    
    if 'Metodología:' in r[0]:
        # Extraer secciones relevantes
        lines = r[0].split('\n')
        for line in lines:
            if any(emoji in line for emoji in ['📌', '👥', '🧩', '💶', '⚠️']):
                print(line)
