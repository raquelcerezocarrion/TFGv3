from backend.engine.brain import generate_reply

casos = [
    ('app de citas', 'APP CITAS'),
    ('startup mvp red social mascotas', 'STARTUP MVP'),
    ('sistema soporte 24/7 tickets', 'SOPORTE 24/7'),
    ('plataforma b2b pedidos empresas', 'B2B'),
    ('plataforma saas con suscripciones', 'SAAS'),
    ('app gimnasio reservas pagos', 'GIMNASIO'),
]

for query, label in casos:
    r = generate_reply(f's_{label}', query)
    if 'Metodología:' in r[0]:
        met = r[0].split('Metodología: ')[1].split('\n')[0]
    else:
        met = 'NO GENERADA'
    print(f'{label:20} → {met}')
