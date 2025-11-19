from backend.engine.brain import generate_reply

print("\n🎯 PRUEBA RÁPIDA - Casos Específicos\n")

casos = [
    "necesito una app bancaria con pagos y seguridad",
    "sistema de seguros para gestionar pólizas",
    "plataforma de delivery de comida con riders",
    "tienda online retail con punto de venta",
    "app de videojuegos multijugador",
]

for i, query in enumerate(casos, 1):
    r = generate_reply(f's{i}', query)
    if 'Metodología:' in r[0]:
        met = r[0].split('Metodología: ')[1].split('\n')[0]
        print(f"{i}. {query[:50]:50} → {met}")
    else:
        print(f"{i}. {query[:50]:50} → NO GENERADA")
