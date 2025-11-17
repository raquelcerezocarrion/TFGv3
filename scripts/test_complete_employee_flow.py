#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test completo del flujo de empleados con API real.
1. Crear empleados en BD (simulando la sección Empleados)
2. Generar propuesta
3. Aceptar propuesta
4. Elegir "usar empleados guardados"
5. Sistema carga empleados y genera asignación
"""

import sys
import os
import io

# Configurar stdout para UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Añadir directorio raíz al path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.memory import state_store
from backend.engine.brain import generate_reply

def print_section(title):
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}\n")

def print_response(step, user_text, reply, label):
    print(f"\n{'─'*80}")
    print(f"PASO {step}: Usuario dice: \"{user_text}\"")
    print(f"{'─'*80}")
    print(f"LABEL: {label}")
    print(f"RESPUESTA:\n{reply[:500]}...")  # Truncar para legibilidad
    print(f"{'─'*80}\n")

def test_complete_flow():
    """Test completo del flujo."""
    
    print_section("TEST COMPLETO DE FLUJO DE EMPLEADOS")
    
    # PASO 0: Crear empleados en base de datos (simulando usuario registrado con user_id=1)
    print_section("PASO 0: Creando empleados en la base de datos")
    
    # Limpiar empleados anteriores del usuario 1
    existing = state_store.list_employees(user_id=1)
    for emp in existing:
        state_store.delete_employee(user_id=1, employee_id=emp.id)
    
    # Crear 4 empleados
    employees_data = [
        {
            "name": "Ana Ruiz",
            "role": "Backend",
            "skills": "Python, Django, PostgreSQL, REST APIs",
            "seniority": "Senior",
            "availability_pct": 100
        },
        {
            "name": "Luis Pérez",
            "role": "QA",
            "skills": "Testing, Selenium, pytest",
            "seniority": "Semi Senior",
            "availability_pct": 50
        },
        {
            "name": "María García",
            "role": "Frontend",
            "skills": "React, TypeScript, CSS",
            "seniority": "Senior",
            "availability_pct": 80
        },
        {
            "name": "Carlos López",
            "role": "Backend",
            "skills": "Python, FastAPI, MongoDB",
            "seniority": "Mid",
            "availability_pct": 100
        }
    ]
    
    for emp_data in employees_data:
        emp = state_store.create_employee(
            user_id=1,
            name=emp_data["name"],
            role=emp_data["role"],
            skills=emp_data["skills"],
            seniority=emp_data["seniority"],
            availability_pct=emp_data["availability_pct"]
        )
        print(f"✅ Creado: {emp.name} - {emp.role} ({emp.seniority}, {emp.availability_pct}%)")
    
    print(f"\n📊 Total empleados en BD: {len(state_store.list_employees(user_id=1))}")
    
    # PASO 1: Generar propuesta
    print_section("PASO 1: Generar propuesta")
    session_id = "test_complete_flow"
    text1 = "Necesito una app bancaria con pagos móviles y seguridad robusta"
    reply1, label1 = generate_reply(session_id, text1)
    print_response(1, text1, reply1, label1)
    
    if "metodología" not in reply1.lower():
        print("❌ ERROR: No se generó propuesta")
        return False
    
    # PASO 2: Aceptar propuesta
    print_section("PASO 2: Aceptar propuesta")
    text2 = "acepto la propuesta"
    reply2, label2 = generate_reply(session_id, text2)
    print_response(2, text2, reply2, label2)
    
    if "empleados guardados" not in reply2.lower() or "manual" not in reply2.lower():
        print("❌ ERROR: No pregunta por método de staffing")
        return False
    
    # PASO 3: Elegir usar empleados guardados
    print_section("PASO 3: Elegir 'usar empleados guardados'")
    text3 = "usar empleados guardados"
    reply3, label3 = generate_reply(session_id, text3)
    print_response(3, text3, reply3, label3)
    
    if "json" not in reply3.lower():
        print("❌ ERROR: No pide JSON de empleados")
        return False
    
    # PASO 4: Enviar JSON de empleados (simulando lo que haría el frontend)
    print_section("PASO 4: Enviar JSON de empleados")
    
    # Cargar empleados de la BD y convertir a JSON
    employees_from_db = state_store.list_employees(user_id=1)
    employees_json_list = [
        {
            "name": emp.name,
            "role": emp.role,
            "skills": emp.skills,
            "seniority": emp.seniority,
            "availability_pct": emp.availability_pct
        }
        for emp in employees_from_db
    ]
    
    import json
    text4 = json.dumps(employees_json_list, indent=2, ensure_ascii=False)
    print(f"JSON a enviar:\n{text4}\n")
    
    reply4, label4 = generate_reply(session_id, text4)
    print_response(4, "JSON de empleados", reply4, label4)
    
    # Verificaciones
    if "metodología" in reply4.lower() and ("xp" in reply4.lower() or "scrum" in reply4.lower()):
        # Si contiene metodología, probablemente generó una NUEVA propuesta (MAL)
        if "asignación" not in reply4.lower() and "cargado" not in reply4.lower():
            print("❌ ERROR: Generó NUEVA propuesta en lugar de asignar empleados")
            return False
    
    if "asignación" not in reply4.lower() and "cargado" not in reply4.lower():
        print("❌ ERROR: No procesó los empleados correctamente")
        return False
    
    # Verificar que aparecen los nombres de los empleados en la respuesta
    employees_found = sum(1 for emp in employees_data if emp["name"] in reply4)
    print(f"\n📊 Empleados encontrados en la respuesta: {employees_found}/{len(employees_data)}")
    
    if employees_found < 2:
        print("⚠️ ADVERTENCIA: Pocos empleados aparecen en la asignación")
    
    print_section("✅ FLUJO COMPLETO EXITOSO")
    print(f"""
Resumen:
- ✅ Empleados creados en BD: {len(employees_from_db)}
- ✅ Propuesta generada correctamente
- ✅ Aceptación detectada
- ✅ Opción de empleados guardados funcionando
- ✅ JSON procesado y asignación generada
- 📊 {employees_found}/{len(employees_data)} empleados aparecen en la asignación
    """)
    
    return True

if __name__ == "__main__":
    try:
        success = test_complete_flow()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ ERROR INESPERADO: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
