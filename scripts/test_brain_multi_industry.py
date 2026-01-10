"""
Script para probar el flujo completo del asistente con ejemplos multi-industria.
Este script simula lo que haría el usuario desde el chat frontend.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.engine.brain import generate_reply
import json

# Caso de prueba: Marketing Tech
test_message_marketing = """
Quiero crear una plataforma de email marketing automation tipo Mailchimp.
Segmentación avanzada de audiencias, A/B testing de campañas, analytics en tiempo real,
integración con Google Analytics, Facebook Ads y Google Ads. Cumplimiento GDPR.
Dashboard con métricas de conversión y ROI. Automatización de workflows.
"""

# Caso de prueba: Farmacia
test_message_pharma = """
Necesito una farmacia online con venta de medicamentos y recetas electrónicas.
Debe cumplir con FDA y regulación farmacéutica española. Sistema de verificación
de recetas médicas, trazabilidad de lotes, alertas de interacciones medicamentosas,
gestión de stock con caducidades. Integración con sistemas de salud existentes.
"""

# Caso de prueba: Gaming
test_message_gaming = """
Juego mobile casual tipo Candy Crush pero con temática espacial. Multijugador
con matchmaking, leaderboards globales, sistema de temporadas y eventos,
in-app purchases, chat en tiempo real. Anti-cheat obligatorio. Despliegues
semanales con nuevos niveles. Analytics detallado de comportamiento de jugadores.
"""

def test_brain_with_industry(message: str, industry_name: str):
    """
    Prueba el brain del asistente con un mensaje específico de industria
    """
    print("=" * 80)
    print(f"🧪 PROBANDO: {industry_name}")
    print("=" * 80)
    print(f"\n📝 Mensaje del usuario:")
    print(message.strip())
    
    session_id = f"test-{industry_name.lower().replace(' ', '-')}-001"
    
    try:
        # Procesar mensaje (esto es lo que hace el backend cuando recibe un chat)
        message_response, action = generate_reply(session_id, message)
        
        print(f"\n✅ Respuesta del asistente:")
        print("-" * 80)
        print(message_response)
        print("-" * 80)
        print(f"\nAcción: {action}")
        
        print(f"\n✅ PRUEBA EXITOSA para {industry_name}")
        return True
        
    except Exception as e:
        print(f"\n❌ ERROR en prueba de {industry_name}:")
        print(str(e))
        import traceback
        traceback.print_exc()
        return False


def main():
    print("\n" + "=" * 80)
    print("🚀 PRUEBA INTEGRAL DEL ASISTENTE MULTI-INDUSTRIA")
    print("=" * 80)
    print("\nEste script prueba el flujo completo: mensaje → brain → propuesta\n")
    
    results = []
    
    # Probar Marketing Tech
    results.append(test_brain_with_industry(test_message_marketing, "Marketing Tech"))
    print("\n" * 2)
    
    # Probar Farmacia
    results.append(test_brain_with_industry(test_message_pharma, "Farmacia/Pharma"))
    print("\n" * 2)
    
    # Probar Gaming
    results.append(test_brain_with_industry(test_message_gaming, "Gaming"))
    print("\n" * 2)
    
    # Resumen final
    print("=" * 80)
    print("📊 RESUMEN DE PRUEBAS")
    print("=" * 80)
    
    exitosas = sum(results)
    total = len(results)
    
    print(f"\n✅ Exitosas: {exitosas}/{total}")
    print(f"❌ Fallidas: {total - exitosas}/{total}")
    
    if exitosas == total:
        print("\n🎉 ¡TODAS LAS PRUEBAS PASARON! El asistente está listo para producción.")
    else:
        print("\n⚠️  Algunas pruebas fallaron. Revisar los errores arriba.")
    
    return exitosas == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
