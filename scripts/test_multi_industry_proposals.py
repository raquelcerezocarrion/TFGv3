"""
Script para probar propuestas de múltiples industrias:
marketing, consumo, manufactura, farmacia, gaming, energía, etc.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.engine.planner import generate_proposal
import json

# Casos de prueba para diferentes industrias
test_cases = {
    "Marketing Tech": """
        Plataforma de marketing automation para campañas multicanal. 
        Necesita segmentación de audiencias, A/B testing, email marketing, 
        integración con Google Ads y Meta. Analytics en tiempo real, 
        GDPR compliance. ROI tracking y customer journey mapping.
    """,
    
    "Consumer App": """
        App móvil de delivery de comida saludable. iOS y Android nativa.
        Onboarding gamificado, sistema de puntos y recompensas,
        notificaciones push personalizadas, tracking en tiempo real,
        integración con Stripe. Alta retención y engagement críticos.
    """,
    
    "Manufactura/Industria 4.0": """
        Sistema MES (Manufacturing Execution System) para planta de producción.
        Integración con PLCs y SCADA. Control de calidad en tiempo real,
        mantenimiento predictivo con ML, trazabilidad completa de lotes,
        OEE monitoring, alertas y dashboards para supervisores.
    """,
    
    "Farmacia/Pharma": """
        Sistema de gestión farmacéutica con trazabilidad completa de medicamentos.
        Cumplimiento FDA/EMA y GMP (21 CFR Part 11). Gestión de lotes,
        farmacovigilancia, control de reacciones adversas, prescripciones electrónicas,
        integración con sistemas hospitalarios. Validación crítica.
    """,
    
    "Gaming": """
        Juego móvil multijugador casual tipo puzzle-match con elementos sociales.
        Matchmaking, leaderboards, chat en tiempo real, sistema de temporadas,
        in-app purchases, anti-cheat, analytics de jugadores,
        despliegues continuos con A/B testing de features.
    """,
    
    "Energía/Utilities": """
        Sistema de gestión de red eléctrica inteligente (smart grid).
        Integración con smart meters, SCADA para subestaciones,
        monitorización en tiempo real, predicción de consumo con ML,
        alertas de fallos, gestión de demanda. Infraestructura crítica 24/7.
    """,
    
    "Automoción": """
        Plataforma telemática para gestión de flotas de vehículos.
        Conectividad vehicular, tracking GPS, diagnóstico OBD-II,
        alertas de mantenimiento preventivo, comportamiento del conductor,
        actualizaciones OTA. Seguridad crítica ISO 26262.
    """,
    
    "Construcción": """
        Software de gestión de proyectos de construcción con BIM.
        Gestión de subcontratistas, control de presupuestos,
        planificación de obra, seguimiento de avances, 
        certificaciones, integración con Revit/AutoCAD.
    """,
    
    "Fashion/Moda": """
        E-commerce de moda con recomendaciones personalizadas.
        Sistema de tallas inteligente, lookbook interactivo,
        gestión de colecciones y temporadas, sincronización multi-canal
        (tienda física + online), AR para prueba virtual de prendas.
    """,
    
    "Sports/Fitness": """
        App de fitness con integración de wearables (Fitbit, Apple Watch).
        Tracking de entrenamientos, análisis biométrico,
        planes personalizados con ML, comunidad y retos,
        integración con nutricionistas, gamificación.
    """,
}

def test_all_industries():
    print("=" * 80)
    print("PRUEBA DE GENERACIÓN DE PROPUESTAS MULTI-INDUSTRIA")
    print("=" * 80)
    
    results = {}
    
    for industry, requirements in test_cases.items():
        print(f"\n{'=' * 80}")
        print(f"INDUSTRIA: {industry}")
        print(f"{'=' * 80}")
        print(f"\nRequisitos:")
        print(requirements.strip())
        
        try:
            proposal = generate_proposal(requirements)
            
            print(f"\n✅ Propuesta generada exitosamente")
            print(f"\nMetodología recomendada: {proposal['methodology']}")
            print(f"Score: {proposal['methodology_score']}")
            
            print(f"\n📋 Equipo ({len(proposal['team'])} roles):")
            for member in proposal['team']:
                print(f"  - {member['role']}: {member['count']}")
            
            print(f"\n📅 Fases ({len(proposal['phases'])} fases):")
            for phase in proposal['phases']:
                print(f"  - {phase['name']}: {phase['weeks']} semanas")
            
            print(f"\n💰 Presupuesto:")
            print(f"  - Labor: €{proposal['budget']['labor_estimate_eur']:,.2f}")
            print(f"  - Contingencia ({proposal['budget']['contingency_pct']}): €{proposal['budget']['contingency_eur']:,.2f}")
            print(f"  - TOTAL: €{proposal['budget']['total_eur']:,.2f}")
            print(f"  - Nota industria: {proposal['budget']['assumptions']['industry_note']}")
            
            print(f"\n⚠️ Riesgos identificados ({len(proposal['risks'])}):")
            for risk in proposal['risks'][:5]:  # Primeros 5
                print(f"  - {risk}")
            if len(proposal['risks']) > 5:
                print(f"  ... y {len(proposal['risks']) - 5} más")
            
            results[industry] = {
                "success": True,
                "methodology": proposal['methodology'],
                "team_size": len(proposal['team']),
                "total_budget": proposal['budget']['total_eur'],
                "risks_count": len(proposal['risks'])
            }
            
        except Exception as e:
            print(f"\n❌ Error generando propuesta: {str(e)}")
            import traceback
            traceback.print_exc()
            results[industry] = {
                "success": False,
                "error": str(e)
            }
    
    # Resumen final
    print(f"\n\n{'=' * 80}")
    print("RESUMEN DE RESULTADOS")
    print(f"{'=' * 80}")
    
    successful = sum(1 for r in results.values() if r.get('success'))
    total = len(results)
    
    print(f"\n✅ Exitosas: {successful}/{total}")
    print(f"❌ Fallidas: {total - successful}/{total}")
    
    print("\n📊 Tabla de resultados:\n")
    print(f"{'Industria':<30} {'Metodología':<15} {'Equipo':<8} {'Presupuesto':<15}")
    print("-" * 80)
    
    for industry, result in results.items():
        if result.get('success'):
            print(f"{industry:<30} {result['methodology']:<15} {result['team_size']:<8} €{result['total_budget']:>12,.0f}")
        else:
            print(f"{industry:<30} {'ERROR':<15} {'-':<8} {'-':<15}")
    
    return results

if __name__ == "__main__":
    results = test_all_industries()
    
    # Guardar resultados
    output_file = os.path.join(os.path.dirname(__file__), '..', 'reports', 'multi_industry_test_results.json')
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Resultados guardados en: {output_file}")
