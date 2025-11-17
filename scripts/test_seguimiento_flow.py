"""Test del flujo completo: generar propuesta → aceptar → asignar empleados → decir 'sí' → verificar propuestas disponibles en Seguimiento.

Uso:
    python scripts/test_seguimiento_flow.py
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import requests
import json

BASE = 'http://localhost:8000'

def test_seguimiento_flow():
    print("=" * 80)
    print("TEST FLUJO SEGUIMIENTO")
    print("=" * 80)
    
    # 1. Register/Login
    print("\n=== PASO 1: Autenticación")
    try:
        requests.post(f"{BASE}/auth/register", json={
            'email': 'test_seguimiento@example.com',
            'password': 'secret123',
            'full_name': 'Test Seguimiento'
        })
    except:
        pass
    
    r = requests.post(f"{BASE}/auth/login", json={
        'email': 'test_seguimiento@example.com',
        'password': 'secret123'
    })
    if r.status_code != 200:
        print(f"❌ Login falló: {r.status_code}")
        return
    token = r.json()['access_token']
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    print(f"✅ Login exitoso")
    
    # 2. Crear empleados
    print("\n=== PASO 2: Crear empleados")
    employees = [
        {'name': 'Ana Ruiz', 'role': 'Backend', 'skills': 'Python, Django, PostgreSQL', 'seniority': 'Senior', 'availability_pct': 100},
        {'name': 'Luis Pérez', 'role': 'QA', 'skills': 'Testing, Selenium', 'seniority': 'Semi Senior', 'availability_pct': 50},
    ]
    for emp in employees:
        r = requests.post(f"{BASE}/user/employees", json=emp, headers=headers)
        if r.status_code == 200:
            print(f"✅ Empleado creado: {emp['name']}")
    
    # 3. Crear chat guardado
    print("\n=== PASO 3: Crear chat guardado")
    r = requests.post(f"{BASE}/user/chats", json={
        'title': 'Test Seguimiento Flow',
        'content': '[]'
    }, headers=headers)
    if r.status_code != 200:
        print(f"❌ No se pudo crear chat: {r.status_code}")
        return
    chat = r.json()
    chat_id = chat['id']
    print(f"✅ Chat creado: ID {chat_id}")
    
    # 4. Continuar chat (obtener session_id)
    print("\n=== PASO 4: Continuar chat")
    r = requests.post(f"{BASE}/user/chats/{chat_id}/continue", headers=headers)
    if r.status_code != 200:
        print(f"❌ No se pudo continuar: {r.status_code}")
        return
    session_id = r.json()['session_id']
    print(f"✅ Session ID: {session_id}")
    
    # 5. Enviar solicitud para generar propuesta via chat HTTP
    print("\n=== PASO 5: Generar propuesta vía chat")
    r = requests.post(f"{BASE}/chat", json={
        'session_id': session_id,
        'message': 'Necesito una app de ecommerce con catálogo, carrito y pagos'
    })
    if r.status_code != 200:
        print(f"❌ Chat falló: {r.status_code}")
        return
    response = r.json()
    print(f"✅ Propuesta generada")
    resp_text = response.get('response') or str(response)
    print(f"   Respuesta (primeros 200 chars): {resp_text[:200]}...")
    
    # 6. Aceptar propuesta
    print("\n=== PASO 6: Aceptar propuesta")
    r = requests.post(f"{BASE}/chat", json={
        'session_id': session_id,
        'message': 'acepto la propuesta'
    })
    if r.status_code == 200:
        print(f"✅ Propuesta aceptada")
        resp = r.json().get('response') or str(r.json())
        print(f"   Respuesta: {resp[:150]}...")
    
    # 7. Elegir usar empleados guardados
    print("\n=== PASO 7: Elegir usar empleados guardados")
    r = requests.post(f"{BASE}/chat", json={
        'session_id': session_id,
        'message': 'usar empleados guardados'
    })
    if r.status_code == 200:
        print(f"✅ Solicitud de empleados guardados enviada")
    
    # 8. Enviar JSON de empleados
    print("\n=== PASO 8: Enviar JSON de empleados")
    r = requests.get(f"{BASE}/user/employees", headers=headers)
    emps_json = r.json()
    r = requests.post(f"{BASE}/chat", json={
        'session_id': session_id,
        'message': json.dumps(emps_json)
    })
    if r.status_code == 200:
        resp = r.json().get('response') or str(r.json())
        print(f"✅ Asignación recibida")
        print(f"   Respuesta (primeros 300 chars): {resp[:300]}...")
    
    # 9. Decir "sí" para comenzar proyecto
    print("\n=== PASO 9: Confirmar inicio del proyecto")
    r = requests.post(f"{BASE}/chat", json={
        'session_id': session_id,
        'message': 'sí'
    })
    if r.status_code == 200:
        resp = r.json().get('response') or str(r.json())
        print(f"✅ Confirmación enviada")
        print(f"   Respuesta: {resp[:200]}...")
    
    # 10. Verificar que el chat tiene propuestas guardadas
    print("\n=== PASO 10: Verificar propuestas en /projects/from_chat/{chat_id}")
    print(f"   Chat ID: {chat_id}")
    print(f"   Session pattern esperado: saved-{chat_id}-%")
    r = requests.get(f"{BASE}/projects/from_chat/{chat_id}")
    if r.status_code == 200:
        proposals = r.json()
        print(f"✅ Propuestas encontradas: {len(proposals)}")
        if len(proposals) == 0:
            print("   ⚠️ No se encontraron propuestas. Verificando ProposalLog directamente...")
            # Intentar listar todas las propuestas recientes
            r_all = requests.get(f"{BASE}/projects/list?session_id={session_id}")
            if r_all.status_code == 200:
                all_props = r_all.json()
                print(f"   📊 Propuestas en session {session_id}: {len(all_props)}")
                for p in all_props:
                    print(f"      - ID: {p.get('id')}, Metodología: {p.get('methodology')}")
        
        for p in proposals:
            print(f"   - ID: {p.get('id')}, Metodología: {p.get('methodology')}")
            
            # 11. Obtener fases de la propuesta
            if p.get('id'):
                print(f"\n=== PASO 11: Obtener fases de propuesta {p['id']}")
                r_phases = requests.get(f"{BASE}/projects/{p['id']}/phases")
                if r_phases.status_code == 200:
                    phases = r_phases.json()
                    print(f"✅ Fases encontradas: {len(phases)}")
                    for idx, phase in enumerate(phases):
                        print(f"   {idx+1}. {phase.get('name')} ({phase.get('weeks', '?')} semanas)")
                else:
                    print(f"⚠️ No se pudieron obtener fases: {r_phases.status_code}")
    else:
        print(f"❌ No se pudieron obtener propuestas: {r.status_code}")
    
    print("\n" + "=" * 80)
    print("✅ TEST COMPLETADO")
    print("=" * 80)

if __name__ == '__main__':
    test_seguimiento_flow()
