"""
Ejemplos de prompts para probar las nuevas capacidades multi-industria del asistente.
Estos son mensajes reales que un usuario podría enviar.
"""

EJEMPLOS_REALES = {
    
    "farmacia_online": """
    Necesito una farmacia online con venta de medicamentos y recetas electrónicas.
    Debe cumplir con FDA y regulación farmacéutica española. Sistema de verificación
    de recetas médicas, trazabilidad de lotes, alertas de interacciones medicamentosas,
    gestión de stock con caducidades. Integración con sistemas de salud existentes.
    """,
    
    "plataforma_marketing": """
    Quiero crear una plataforma de email marketing automation tipo Mailchimp.
    Segmentación avanzada de audiencias, A/B testing de campañas, analytics en tiempo real,
    integración con Google Analytics, Facebook Ads y Google Ads. Cumplimiento GDPR.
    Dashboard con métricas de conversión y ROI. Automatización de workflows.
    """,
    
    "app_fitness": """
    App móvil de entrenamiento personalizado con integración de Apple Watch y Fitbit.
    Planes de entrenamiento con IA, tracking de progreso, análisis de biometría,
    gamificación con logros y recompensas. Comunidad de usuarios con retos.
    Integración con nutricionistas. iOS y Android nativo.
    """,
    
    "sistema_industrial": """
    Sistema MES para fábrica de automoción. Control de producción en tiempo real,
    integración con PLCs Siemens y SCADA. Trazabilidad completa de componentes,
    mantenimiento predictivo de maquinaria, monitorización de OEE, alertas de calidad.
    Dashboard para supervisores de planta. Cumplimiento ISO 9001.
    """,
    
    "juego_mobile": """
    Juego mobile casual tipo Candy Crush pero con temática espacial. Multijugador
    con matchmaking, leaderboards globales, sistema de temporadas y eventos,
    in-app purchases, chat en tiempo real. Anti-cheat obligatorio. Despliegues
    semanales con nuevos niveles. Analytics detallado de comportamiento de jugadores.
    """,
    
    "smart_grid": """
    Sistema de gestión de red eléctrica inteligente. Integración con smart meters
    de millones de hogares, SCADA para subestaciones, predicción de demanda con ML,
    detección de fallos en tiempo real, gestión de energías renovables,
    balanceo de carga. Infraestructura crítica 24/7 con alta disponibilidad.
    """,
    
    "ecommerce_moda": """
    E-commerce de ropa y accesorios de moda. Sistema de recomendaciones personalizadas,
    probador virtual con AR, gestión de tallas inteligente, lookbooks interactivos,
    integración con tiendas físicas para click&collect. Gestión de colecciones
    y temporadas. Sincronización de inventario multi-canal. Stripe y Redsys.
    """,
    
    "software_construccion": """
    Software de gestión de proyectos de construcción. Integración con BIM (Revit, AutoCAD),
    gestión de subcontratistas y proveedores, control de presupuestos y desviaciones,
    planificación de obra con diagrama de Gantt, seguimiento de avances,
    certificaciones de obra. Gestión documental y planos. App móvil para obra.
    """,
    
    "plataforma_telemática": """
    Plataforma de gestión de flotas de vehículos comerciales. Tracking GPS en tiempo real,
    diagnóstico OBD-II de vehículos, alertas de mantenimiento preventivo,
    análisis de comportamiento del conductor, optimización de rutas,
    actualizaciones OTA de firmware. Cumplimiento normas de transporte.
    Dashboard para gestores de flota.
    """,
    
    "app_delivery_food": """
    App tipo Uber Eats para delivery de comida de restaurantes locales.
    Tracking en tiempo real de pedidos, sistema de riders con geolocalización,
    pasarela de pagos (Stripe), chat entre usuario-restaurante-rider,
    sistema de valoraciones, algoritmo de asignación de pedidos,
    panel de administración para restaurantes. Push notifications.
    """,
}


def generar_ejemplos_markdown():
    """Genera un archivo markdown con ejemplos de uso"""
    
    md = """# Ejemplos de Uso Multi-Industria

Este documento contiene ejemplos reales de prompts que se pueden usar con el asistente
para generar propuestas especializadas por industria.

---

"""
    
    industrias = {
        "farmacia_online": "💊 Farmacia Online",
        "plataforma_marketing": "📈 Marketing Automation",
        "app_fitness": "🏃 Fitness & Sports",
        "sistema_industrial": "🏭 Manufactura/Industria 4.0",
        "juego_mobile": "🎮 Gaming",
        "smart_grid": "⚡ Energía/Smart Grid",
        "ecommerce_moda": "👗 Fashion E-commerce",
        "software_construccion": "🏗️ Construcción/BIM",
        "plataforma_telemática": "🚗 Automoción/Telemática",
        "app_delivery_food": "🍔 Food Delivery",
    }
    
    for key, titulo in industrias.items():
        md += f"## {titulo}\n\n"
        md += "**Prompt del usuario:**\n\n"
        md += "```\n"
        md += EJEMPLOS_REALES[key].strip()
        md += "\n```\n\n"
        md += "**El asistente generará:**\n"
        md += "- ✅ Metodología recomendada según contexto\n"
        md += "- ✅ Equipo con roles especializados\n"
        md += "- ✅ Presupuesto ajustado por industria\n"
        md += "- ✅ Riesgos específicos de la industria\n"
        md += "- ✅ Fases adaptadas a las necesidades\n"
        md += "\n---\n\n"
    
    return md


if __name__ == "__main__":
    # Generar archivo de ejemplos
    md_content = generar_ejemplos_markdown()
    
    with open("../EJEMPLOS_MULTI_INDUSTRIA.md", "w", encoding="utf-8") as f:
        f.write(md_content)
    
    print("✅ Archivo de ejemplos generado: EJEMPLOS_MULTI_INDUSTRIA.md")
    print(f"\n📊 Total de ejemplos: {len(EJEMPLOS_REALES)}")
    print("\nIndustrias cubiertas:")
    for i, key in enumerate(EJEMPLOS_REALES.keys(), 1):
        print(f"  {i}. {key}")
