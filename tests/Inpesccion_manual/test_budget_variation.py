from backend.engine.brain import generate_reply
import json

print("╔═════════════════════════════════════════════════════════════════════════════════╗")
print("║          VERIFICACIÓN DE VARIACIÓN DE PRESUPUESTO POR INDUSTRIA                ║")
print("╚═════════════════════════════════════════════════════════════════════════════════╝\n")

casos = [
    ("app bancaria para transferencias", "FINTECH"),
    ("sistema de seguros para pólizas", "INSURTECH"),
    ("plataforma de telemedicina", "HEALTHTECH"),
    ("plataforma e-learning", "EDTECH"),
    ("sistema de tracking logístico", "LOGISTICS"),
    ("punto de venta retail", "RETAIL"),
    ("app de delivery de comida", "FOOD DELIVERY"),
    ("videojuego multijugador", "GAMING"),
    ("ERP enterprise", "ERP"),
    ("startup mvp red social", "STARTUP"),
]

print(f"{'INDUSTRIA':20} | {'METODOLOGÍA':10} | {'EQUIPO':6} | {'SEMANAS':7} | {'PRESUPUESTO':15} | {'CONTINGENCIA':12}")
print("=" * 95)

for query, label in casos:
    r = generate_reply(f's_{label}', query)
    
    if 'Metodología:' in r[0]:
        # Extraer metodología
        met = r[0].split('Metodología: ')[1].split('\n')[0].strip()
        
        # Extraer equipo (contar roles)
        if '👥 Equipo:' in r[0]:
            equipo_line = r[0].split('👥 Equipo: ')[1].split('\n')[0]
            team_count = equipo_line.count('x')
        else:
            team_count = 0
        
        # Extraer presupuesto
        if '💶 Presupuesto:' in r[0]:
            presupuesto_line = r[0].split('💶 Presupuesto: ')[1].split(' €')[0].strip()
        else:
            presupuesto_line = "N/A"
        
        # Extraer fases para calcular semanas
        if '🧩 Fases:' in r[0]:
            fases_line = r[0].split('🧩 Fases: ')[1].split('\n')[0]
            # Contar semanas sumando los números seguidos de 's)'
            import re
            semanas = sum([int(s) for s in re.findall(r'(\d+)s\)', fases_line)])
        else:
            semanas = 0
        
        # Extraer contingencia del texto
        contingencia = "10%"  # default
        if "15% contingencia" in r[0]:
            contingencia = "15%"
        elif "12% contingencia" in r[0]:
            contingencia = "12%"
        elif "20% contingencia" in r[0]:
            contingencia = "20%"
        elif "incluye 10% contingencia" in r[0]:
            contingencia = "10%"
        
        print(f"{label:20} | {met:10} | {team_count:6} | {semanas:7} | {presupuesto_line:>15} | {contingencia:>12}")
    else:
        print(f"{label:20} | NO GENERADA")

print("\n" + "=" * 95)
print("OBSERVACIONES:")
print("- FINTECH/HEALTHTECH/INSURTECH: Tarifas +30%, contingencia 15%, más QA/Security")
print("- ERP/ENTERPRISE: Duración +40%, más arquitectos")
print("- GAMING/MEDIA: Tarifas +15%, DevOps adicional")
print("- STARTUP: Tarifas -10%, duración -20%, contingencia 20% (incertidumbre)")
print("- LOGISTICS/RETAIL: Tarifas -5% (mercado competitivo)")
