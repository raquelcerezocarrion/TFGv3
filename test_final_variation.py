from backend.engine.brain import generate_reply

print("╔═══════════════════════════════════════════════════════════════════════════╗")
print("║           VERIFICACIÓN DE VARIACIÓN DE METODOLOGÍAS                      ║")
print("╚═══════════════════════════════════════════════════════════════════════════╝\n")

casos = [
    ('app de citas con algoritmo de matching', 'DATING APP'),
    ('startup mvp red social', 'STARTUP SOCIAL'),
    ('sistema soporte 24/7 tickets', 'SOPORTE 24/7'),
    ('plataforma b2b pedidos', 'B2B PEDIDOS'),
    ('plataforma saas suscripciones', 'SAAS'),
    ('app gimnasio reservas pagos', 'GIMNASIO'),
    ('ecommerce tienda online carrito', 'ECOMMERCE'),
    ('sistema bancario alta seguridad', 'BANKING'),
    ('marketplace vendedores compradores', 'MARKETPLACE'),
    ('proyecto pequeño landing page', 'LANDING'),
]

metodologias_encontradas = set()

for query, label in casos:
    r = generate_reply(f's_{label}', query)
    if 'Metodología:' in r[0]:
        met = r[0].split('Metodología: ')[1].split('\n')[0]
    else:
        met = 'NO GENERADA'
    
    metodologias_encontradas.add(met)
    print(f'{label:20} → {met:15} | Query: {query[:40]}...')

print(f"\n{'='*80}")
print(f"Metodologías diferentes encontradas: {len(metodologias_encontradas)}")
print(f"Lista: {', '.join(sorted(metodologias_encontradas))}")
print(f"{'='*80}")
