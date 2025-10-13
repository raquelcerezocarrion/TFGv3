import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import os


def generate_methodology_chart(methodology: str, out_path: str = "methodology_chart.png", data: dict = None):
    """Generate a chart for the given methodology using optional data.

    data can contain:
      - 'phases': either a dict {phase: weeks} or a string like 'Discovery 2s • Iteraciones 6s • Hardening 2s'
      - 'weeks_total': total weeks
    """
    if not methodology:
        return None
    m = (methodology or "").lower()

    # normalize phases data
    phases_map = {}
    if data:
        if isinstance(data.get("phases"), dict):
            phases_map = data.get("phases")
        elif isinstance(data.get("phases"), str):
            # parse patterns like 'Discovery 2s • Iteraciones 6s • Hardening 2s' or using arrows
            import re
            raw = data.get("phases")
            # split on common separators: bullets, commas, semicolons, arrows, dashes
            parts = re.split(r"\s*(?:[•·,;\|]|->|→|–|—|\-)\s*", raw)
            for p in parts:
                if not p or p.strip() == "":
                    continue
                # find a number like 2 or 2.5 possibly followed by 's' and possibly inside parentheses
                week_m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*s?\b", p)
                if week_m:
                    try:
                        weeks = float(week_m.group(1))
                    except Exception:
                        weeks = None
                    # remove the weeks part and any surrounding parentheses to get the name
                    name = re.sub(r"\(?\s*%s\s*s?\s*\)?" % re.escape(week_m.group(1)), "", p)
                    name = name.replace('()', '').strip()
                    if name:
                        phases_map[name] = int(weeks) if weeks is not None else weeks
    # fallback default phases
    if not phases_map:
        if "scrum" in m:
            phases_map = {"Discovery": 2, "Iteraciones": 6, "Hardening": 2, "Release": 1}
        elif "kanban" in m:
            phases_map = {"Discovery": 2, "Flujo": 8, "QA": 1, "Release": 1}
        elif "waterfall" in m or "cascada" in m:
            phases_map = {"Req": 2, "Design": 3, "Build": 4, "Test": 3, "Deploy": 1}
        else:
            phases_map = {"Discovery": 2, "Iteraciones": 6, "Hardening": 2, "Release": 1}

    phases = list(phases_map.keys())
    durations = list(phases_map.values())

    # create visuals per methodology type
    mm = m.lower()
    # scale height with number of phases for readability
    n_phases = max(1, len(phases))
    height = max(2.8, 0.6 * n_phases)
    fig = plt.figure(figsize=(9, height))
    ax = fig.add_subplot(111)

    # Helper to draw timeline (stacked horizontal bars)
    def draw_timeline(phases, durations, color="#4c78a8", title=None):
        # Draw one vertical bar per phase, each with a different color
        try:
            cmap = plt.get_cmap("tab20")
            base_colors = list(cmap.colors)
        except Exception:
            base_colors = [color]
        color_list = [base_colors[i % len(base_colors)] for i in range(len(phases))]

        ax.clear()
        x = list(range(len(phases)))
        bars = ax.bar(x, durations, color=color_list, edgecolor='black')

        # labels and ticks
        ax.set_xticks(x)
        # wrap long phase names
        import textwrap
        wrapped_labels = ["\n".join(textwrap.wrap(p, 20)) for p in phases]
        ax.set_xticklabels(wrapped_labels, rotation=0, fontsize=9)

        ax.set_ylabel("Semanas")
        if title:
            ax.set_title(title)

        # annotate durations above each bar
        for rect, d in zip(bars, durations):
            h = rect.get_height()
            ax.text(rect.get_x() + rect.get_width() / 2.0, h + 0.05 * max(1, sum(durations)), f"{int(d)}s", ha='center', va='bottom', fontsize=9, fontweight='bold')

    # Specific visuals
    if "scrum" in mm:
        draw_timeline(phases, durations, color="#4c78a8", title=f"Plan por sprints (Scrum)")

    elif "kanban" in mm or "kanban" in mm:
        # Kanban: show columns as bars (not timeline)
        cols = phases or ["Backlog", "Ready", "Doing", "Review", "Done"]
        vals = durations if durations and len(durations) == len(cols) else [20, 10, 30, 20, 20]
        ax.clear()
        ax.bar(cols, vals, color="#54a24b")
        ax.set_title("Flujo Kanban — WIP estimado por columna")
        ax.set_ylabel("Ítems (estimado)")

    elif "waterfall" in mm or "cascada" in mm:
        draw_timeline(phases, durations, color="#f58518", title="Fases secuenciales (Waterfall)")

    elif "lean" in mm:
        # Lean: emphasize flow and small batches
        draw_timeline(phases, durations, color="#2ca02c", title="Flujo Lean — fases")

    elif "safe" in mm or "saf" in mm or "scaled" in mm:
        # SAFe style: multiple ARTs / synchronized increments
        cols = phases or ["PI Planning", "Iterations", "Integration", "Release"]
        vals = durations if durations and len(durations) == len(cols) else [2, 8, 2, 1]
        ax.clear()
        ax.bar(cols, vals, color="#e377c2")
        ax.set_title("SAFe — PI / Iterations overview")

    elif "xp" in mm or "extreme" in mm:
        draw_timeline(phases, durations, color="#9467bd", title="XP — Iterative/continuous")

    else:
        draw_timeline(phases, durations, color="#9b59b6", title=f"Plan por fases ({methodology})")

    plt.tight_layout()
    out_dir = os.path.dirname(os.path.abspath(out_path)) or os.getcwd()
    os.makedirs(out_dir, exist_ok=True)
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return out_path


def generate_methodology_diagram(methodology: str, out_path: str = "methodology_diagram.png", data: dict = None):
    """Generate a diagram with chevron arrows for phases and boxes with bullets below.

    Expects data['phases'] either as dict {phase: weeks} or string (parsed), and optionally
    data['phase_contents'] as dict {phase: [bullet1, bullet2,...]}.
    """
    import matplotlib.patches as mpatches
    import textwrap

    if not methodology:
        return None
    # normalize phases
    phases_map = {}
    if data and isinstance(data.get("phases"), dict):
        phases_map = data.get("phases")
    elif data and isinstance(data.get("phases"), str):
        # reuse parser logic from above
        import re
        raw = data.get("phases")
        parts = re.split(r"\s*(?:[•·,;\|]|->|→|–|—|\-)\s*", raw)
        for p in parts:
            if not p.strip():
                continue
            week_m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*s?\b", p)
            if week_m:
                try:
                    weeks = float(week_m.group(1))
                except Exception:
                    weeks = 0
                name = re.sub(r"\(?\s*%s\s*s?\s*\)?" % re.escape(week_m.group(1)), "", p).strip()
                phases_map[name] = int(weeks)
    if not phases_map:
        # fallback
        phases_map = {"Discovery": 2, "Iteraciones": 6, "Hardening": 2, "Release": 1}

    phases = list(phases_map.keys())
    durations = list(phases_map.values())
    n = len(phases)

    fig_w = max(10, 3 * n)
    # compute required height based on potential content: base + lines*0.18
    # estimate max lines in phase contents
    phase_contents = (data or {}).get('phase_contents') or (data or {}).get('phase_details') or {}
    max_lines = 0
    for pname in phases:
        contents = phase_contents.get(pname) if isinstance(phase_contents, dict) else None
        if not contents:
            continue
        # estimate lines per bullet with wrap width 30
        import textwrap
        lines = 0
        for line in contents:
            wrapped = textwrap.wrap(line, width=30)
            lines += max(1, len(wrapped))
        if lines > max_lines:
            max_lines = lines

    fig_h = max(6, 2.8 + max_lines * 0.25)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.axis('off')

    # draw chevrons across the top
    total = sum(durations) or 1
    left = 0.05
    right = 0.95
    width = right - left
    # compute relative widths proportional to duration
    rel = [d / total for d in durations]
    xpos = left
    chev_h = 0.22
    for i, (pname, r) in enumerate(zip(phases, rel)):
        w = r * width
        # draw a chevron as a polygon (points)
        # chevron points: left, mid-left, tip, mid-right, right
        x0 = xpos
        x1 = xpos + w
        # create a trapezoid with a pointed right end
        tip = x1
        points = [
            (x0, 0.85),
            (x1 - 0.06, 0.85),
            (tip, 0.95),
            (x1 - 0.06, 0.75),
            (x0, 0.75),
        ]
        poly = mpatches.Polygon(points, closed=True, facecolor=plt.get_cmap('tab20')(i % 20), edgecolor='black')
        ax.add_patch(poly)
        # label centered on the chevron
        cx = x0 + w * 0.5
        ax.text(cx, 0.82, pname, ha='center', va='center', color='white', fontsize=12, fontweight='bold')
        # duration label under the chevron
        ax.text(cx, 0.70, f"{durations[i]}s", ha='center', va='center', color='black', fontsize=10, fontweight='bold')
        xpos += w

    # draw boxes below with bullets
    box_y = 0.35
    pad = 0.02
    # compute box height based on max_lines (in figure coords)
    # base box height: 0.18 for 1-2 lines, add 0.08 per extra line
    if max_lines <= 0:
        box_h = 0.28
    else:
        box_h = min(0.45, 0.18 + max_lines * 0.08)
    phase_contents = (data or {}).get('phase_contents') or (data or {}).get('phase_details') or {}
    for i, pname in enumerate(phases):
        # horizontal position roughly same as chevron
        rel_w = rel[i]
        bx = left + sum(rel[:i])
        bw = rel_w * width
        # draw rounded rectangle
        rect = mpatches.FancyBboxPatch((bx + pad, box_y), bw - 2 * pad, box_h,
                                      boxstyle='round,pad=0.02', linewidth=1.0, edgecolor='grey', facecolor='white')
        ax.add_patch(rect)
        # add bullet text inside, wrapping per line
        contents = phase_contents.get(pname) if isinstance(phase_contents, dict) else None
        if not contents:
            contents = []
        # compose text with bullets, wrap lines
        txt_lines = []
        for line in contents:
            wrapped = textwrap.wrap(line, width=30)
            if not wrapped:
                txt_lines.append('')
            else:
                for j, w in enumerate(wrapped):
                    if j == 0:
                        txt_lines.append(f'• {w}')
                    else:
                        txt_lines.append(f'  {w}')
        txt = '\n'.join(txt_lines)
        ax.text(bx + bw * 0.02, box_y + box_h - 0.04, txt, va='top', ha='left', fontsize=9)

    plt.tight_layout()
    out_dir = os.path.dirname(os.path.abspath(out_path)) or os.getcwd()
    os.makedirs(out_dir, exist_ok=True)
    fig.savefig(out_path, dpi=300, bbox_inches='tight')
    plt.close(fig)
    return out_path


if __name__ == "__main__":
    generate_methodology_chart("Scrum", "methodology_chart.png")
