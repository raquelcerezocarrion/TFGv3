import unicodedata
import copy

def _norm(s: str) -> str:
    if s is None:
        return ""
    nk = unicodedata.normalize('NFKD', s.lower())
    return ''.join(c for c in nk if not unicodedata.combining(c)).strip()

_ROLE_SYNONYMS = {
    "qa": "QA", "quality": "QA", "tester": "QA",
}

def _canonical_role(role_text: str) -> str:
    t = _norm(role_text)
    for k, v in _ROLE_SYNONYMS.items():
        if k in t:
            return v
    return role_text.strip().title()

# Simular propuesta con equipo
proposal = {
    "team": [
        {"role": "PM", "count": 1.0},
        {"role": "Backend Dev", "count": 2.0},
        {"role": "QA", "count": 1.0}
    ]
}

# Simular patch para cambiar QA a x2
patch = {
    "type": "team",
    "ops": [{"op": "set", "role": "QA", "count": 2.0}]
}

print("Propuesta inicial:")
print(f"  Team: {proposal['team']}")

# Aplicar patch (simulando _apply_patch)
p = copy.deepcopy(proposal)
ops = patch.get("ops", [])

# Normalizar roles
for op in ops:
    original = op["role"]
    op["role"] = _canonical_role(op["role"])
    print(f"\n✓ Normalizando op['role']: {repr(original)} -> {repr(op['role'])}")

# Crear índice de roles
print(f"\nCreando role_index con .lower():")
role_index = {r["role"].lower(): i for i, r in enumerate(p.get("team", []))}
print(f"  role_index = {role_index}")

# Aplicar operación
for op in ops:
    rkey = op["role"].lower()
    print(f"\nBuscando rkey={repr(rkey)} en role_index:")
    if rkey in role_index:
        print(f"  ✓ ENCONTRADO en índice {role_index[rkey]}")
        p["team"][role_index[rkey]]["count"] = float(op["count"])
    else:
        print(f"  ✗ NO ENCONTRADO - agregando nuevo rol")
        p["team"].append({"role": op["role"], "count": float(op["count"])})

print(f"\nPropuesta final:")
print(f"  Team: {p['team']}")
