from backend.engine.brain import generate_reply

print("╔═════════════════════════════════════════════════════════════════════════════════╗")
print("║          VERIFICACIÓN DE METODOLOGÍAS POR TEMÁTICA/INDUSTRIA                   ║")
print("╚═════════════════════════════════════════════════════════════════════════════════╝\n")

casos_por_industria = [
    # FINTECH
    ("app bancaria para transferencias y cuentas digitales", "FINTECH - Banca digital"),
    ("plataforma de trading e inversiones en bolsa", "FINTECH - Trading"),
    ("wallet digital con pagos y criptomonedas", "FINTECH - Wallet crypto"),
    
    # INSURTECH
    ("sistema de seguros para polizas y siniestros", "INSURTECH - Seguros"),
    ("app para reclamaciones de seguros de coche", "INSURTECH - Auto"),
    
    # HEALTHTECH
    ("plataforma de telemedicina para consultas médicas", "HEALTHTECH - Telemedicina"),
    ("sistema hospital para historia clínica pacientes", "HEALTHTECH - Hospital"),
    
    # EDTECH
    ("plataforma e-learning con cursos y examenes", "EDTECH - LMS"),
    ("app educativa para estudiantes y profesores", "EDTECH - App educativa"),
    
    # LOGISTICS
    ("sistema de logística para tracking de paquetes", "LOGISTICS - Tracking"),
    ("plataforma de gestión de flota y rutas", "LOGISTICS - Flota"),
    
    # RETAIL
    ("punto de venta para cadena de tiendas retail", "RETAIL - POS"),
    ("app para franquicias de moda y ropa", "RETAIL - Moda"),
    
    # TRAVEL
    ("plataforma de reservas de hoteles y vuelos", "TRAVEL - Booking"),
    ("app de tours y agencia de viajes", "TRAVEL - Tours"),
    
    # FOOD DELIVERY
    ("app de delivery de comida para restaurantes", "FOOD DELIVERY - Comida"),
    ("sistema de reparto con riders y pedidos", "FOOD DELIVERY - Riders"),
    
    # REAL ESTATE
    ("plataforma inmobiliaria para alquiler y venta", "REAL ESTATE - Inmobiliaria"),
    ("app para gestión de propiedades y tasaciones", "PROPTECH - Gestión"),
    
    # GAMING
    ("videojuego multijugador con rankings", "GAMING - Multiplayer"),
    ("plataforma de esports y torneos", "GAMING - Esports"),
    
    # MEDIA
    ("plataforma de streaming de video y series", "MEDIA - Streaming"),
    ("app de podcasts y contenido multimedia", "MEDIA - Podcasts"),
    
    # IoT
    ("sistema IoT con sensores y telemetría", "IOT - Sensores"),
    ("plataforma de domótica para smart home", "IOT - Smart Home"),
    
    # CRM/ERP/HR
    ("CRM para gestión de leads y ventas", "CRM - Ventas"),
    ("ERP enterprise para contabilidad y recursos", "ERP - Enterprise"),
    ("sistema de recursos humanos y nóminas", "HR TECH - RRHH"),
    
    # OTROS
    ("plataforma legal para abogados y contratos", "LEGAL TECH - Legal"),
    ("sistema agrícola para cultivos y cosecha", "AGRITECH - Agricultura"),
    ("app de eventos y conferencias", "EVENTS - Eventos"),
]

metodologias_count = {}

print(f"{'INDUSTRIA/CASO':55} | {'METODOLOGÍA':15}")
print("=" * 75)

for query, label in casos_por_industria:
    r = generate_reply(f's_{label}', query)
    if 'Metodología:' in r[0]:
        met = r[0].split('Metodología: ')[1].split('\n')[0]
    else:
        met = 'NO GENERADA'
    
    metodologias_count[met] = metodologias_count.get(met, 0) + 1
    print(f"{label:55} | {met:15}")

print("\n" + "=" * 75)
print("RESUMEN DE METODOLOGÍAS ASIGNADAS:")
print("=" * 75)
for met, count in sorted(metodologias_count.items(), key=lambda x: -x[1]):
    print(f"  {met:20} → {count:2} casos")
print("=" * 75)
print(f"Total de metodologías diferentes: {len([m for m in metodologias_count.keys() if m != 'NO GENERADA'])}")
