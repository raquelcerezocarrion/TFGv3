#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test del flujo de asignación de empleados.
Prueba 2 flujos:
1) Generar propuesta → aceptar → usar empleados guardados → enviar JSON
2) Generar propuesta → aceptar → elegir manual
"""

import sys
import os
import io

# Configurar stdout para UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Añadir directorio raíz al path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.engine.brain import generate_reply

def print_response(paso, text, reply, label):
    print(f"\n{'='*80}")
    print(f"PASO {paso}: {text}")
    print(f"{'='*80}")
    print(f"LABEL: {label}")
    print(f"RESPUESTA:\n{reply}")
    print(f"{'='*80}\n")

def test_flujo_empleados_guardados():
    """Prueba el flujo completo con empleados guardados."""
    session_id = "test_employee_flow_saved"
    
    # PASO 1: Generar una propuesta
    text1 = "Necesito una app bancaria con pagos móviles y seguridad robusta"
    reply1, label1 = generate_reply(session_id, text1)
    print_response(1, text1, reply1, label1)
    
    # Verificar que se generó una propuesta
    if "metodología" not in reply1.lower():
        print("❌ ERROR: No se generó una propuesta en PASO 1")
        return False
    
    # PASO 2: Aceptar la propuesta
    text2 = "acepto la propuesta"
    reply2, label2 = generate_reply(session_id, text2)
    print_response(2, text2, reply2, label2)
    
    # Verificar que pregunta por método de staffing
    if "empleados guardados" not in reply2.lower() or "manual" not in reply2.lower():
        print("❌ ERROR: No pregunta por método de staffing en PASO 2")
        return False
    
    # PASO 3: Elegir usar empleados guardados
    text3 = "usar empleados guardados"
    reply3, label3 = generate_reply(session_id, text3)
    print_response(3, text3, reply3, label3)
    
    # Verificar que pide JSON
    if "json" not in reply3.lower():
        print("❌ ERROR: No solicita JSON en PASO 3")
        return False
    
    # PASO 4: Enviar JSON con empleados
    employees_json = """[
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
]"""
    
    text4 = employees_json
    reply4, label4 = generate_reply(session_id, text4)
    print_response(4, text4, reply4, label4)
    
    # Verificar que procesó los empleados (no debe generar nueva propuesta)
    if "metodología" in reply4.lower() and "xp" in reply4.lower():
        print("❌ ERROR: Generó NUEVA propuesta en lugar de procesar empleados")
        return False
    
    if "asignación" not in reply4.lower() and "cargado" not in reply4.lower():
        print("❌ ERROR: No procesó los empleados en PASO 4")
        return False
    
    print("\n✅ FLUJO EMPLEADOS GUARDADOS: OK")
    return True

def test_flujo_manual():
    """Prueba el flujo con entrada manual."""
    session_id = "test_employee_flow_manual"
    
    # PASO 1: Generar una propuesta
    text1 = "Sistema de soporte al cliente con chatbot y ticketing"
    reply1, label1 = generate_reply(session_id, text1)
    print_response(1, text1, reply1, label1)
    
    # PASO 2: Aceptar
    text2 = "acepto"
    reply2, label2 = generate_reply(session_id, text2)
    print_response(2, text2, reply2, label2)
    
    # PASO 3: Elegir manual
    text3 = "manual"
    reply3, label3 = generate_reply(session_id, text3)
    print_response(3, text3, reply3, label3)
    
    # Verificar que pide plantilla manual (debe contener "pega" o "introduce" + "nombre")
    reply3_lower = reply3.lower()
    has_action = ("pega" in reply3_lower or "introduce" in reply3_lower or "lista" in reply3_lower)
    has_format = "nombre" in reply3_lower
    
    if not (has_action and has_format):
        print(f"❌ ERROR: No solicita plantilla manual en PASO 3")
        print(f"   has_action={has_action}, has_format={has_format}")
        return False
    
    print("\n✅ FLUJO MANUAL: OK")
    return True

if __name__ == "__main__":
    print("\n" + "="*80)
    print("TEST FLUJO DE ASIGNACIÓN DE EMPLEADOS")
    print("="*80)
    
    ok1 = test_flujo_empleados_guardados()
    print("\n" + "-"*80 + "\n")
    ok2 = test_flujo_manual()
    
    print("\n" + "="*80)
    if ok1 and ok2:
        print("✅ TODOS LOS TESTS PASARON")
    else:
        print("❌ ALGUNOS TESTS FALLARON")
    print("="*80)
