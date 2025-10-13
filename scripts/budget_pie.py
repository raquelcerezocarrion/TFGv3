import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import gridspec
import textwrap


def create_budget_pie(out_path="budget_pie.png"):
    # Datos proporcionados por el usuario
    semanas_totales = 11
    semanas_por_fase = "Discovery 2s • Iteraciones 6s • Hardening 2s • Release 1s"

    coste_por_rol = {
        "Frontend Dev": 11825.00,
        "QA": 11825.00,
        "PM": 5912.50,
        "Tech Lead": 5912.50,
        "Backend Dev": 5912.50,
        "UX/UI": 5912.50,
    }

    coste_por_actividad = {
        "Iteraciones (build)": 34890.13,
        "Discovery / Historias": 5164.63,
        "Hardening & Aceptación": 5887.46,
        "Release & Handover": 1357.79,
    }

    top_actividades = [
        ("Iteraciones — Frontend Dev", 10455.79),
        ("Iteraciones — QA", 8226.09),
        ("Iteraciones — Backend Dev", 5227.89),
        ("Iteraciones — Tech Lead", 4054.29),
        ("Iteraciones — PM", 3547.50),
    ]

    # Preparar datos del pie
    labels = list(coste_por_rol.keys())
    sizes = list(coste_por_rol.values())

    # Colores
    cmap = plt.get_cmap("tab20c")
    colors = cmap.colors[: len(labels)]

    # Figura con GridSpec: pie arriba a la izquierda, texto a la derecha y debajo
    fig = plt.figure(figsize=(10, 7))
    gs = gridspec.GridSpec(2, 2, height_ratios=[2, 1])

    ax_pie = fig.add_subplot(gs[0, 0])
    ax_text = fig.add_subplot(gs[:, 1])
    ax_bottom = fig.add_subplot(gs[1, 0])

    # Pie chart
    wedges, texts, autotexts = ax_pie.pie(
        sizes,
        labels=None,
        autopct="%1.1f%%",
        startangle=140,
        colors=colors,
        wedgeprops=dict(edgecolor="w"),
        pctdistance=0.75,
        shadow=True,
    )
    ax_pie.set_title("Coste por rol", fontsize=14, fontweight="bold")
    ax_pie.axis("equal")
    plt.setp(autotexts, size=9, weight="bold", color="white")

    # Leyenda al lado del pie
    ax_pie.legend(wedges, [f"{l}: {v:,.2f} €" for l, v in zip(labels, sizes)], loc="center left", bbox_to_anchor=(1, 0.5))

    # Texto derecho: semanas y resumen de coste por actividad
    ax_text.axis("off")
    right_lines = []
    right_lines.append(f"Presupuesto — detalle")
    right_lines.append(f"- Semanas totales: {semanas_totales}")
    right_lines.append(f"- Semanas por fase/actividad: {semanas_por_fase}")
    right_lines.append("")
    right_lines.append("Coste por actividad/fase:")
    for k, v in coste_por_actividad.items():
        right_lines.append(f"- {k}: {v:,.2f} €")

    # Renderizar el texto en el eje derecho
    right_text = "\n".join(right_lines)
    ax_text.text(0, 1, right_text, va="top", ha="left", fontsize=10, wrap=True)

    # Parte inferior: Top actividades (donde se gasta más)
    ax_bottom.axis("off")
    bottom_lines = ["Top actividades (dónde se va más dinero):"]
    for name, val in top_actividades:
        bottom_lines.append(f"- {name}: {val:,.2f} €")
    bottom_text = "\n".join(bottom_lines)
    ax_bottom.text(0, 1, bottom_text, va="top", ha="left", fontsize=10)

    plt.tight_layout()
    fig.savefig(out_path, dpi=300, bbox_inches="tight")


if __name__ == "__main__":
    create_budget_pie()
