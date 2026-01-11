import unicodedata
import re
from typing import List, Dict, Any, Optional

def _norm(s: str) -> str:
    if s is None:
        return ""
    nk = unicodedata.normalize('NFKD', s.lower())
    return ''.join(c for c in nk if not unicodedata.combining(c)).strip()

_ROLE_SYNONYMS = {
    "qa": "QA", "quality": "QA", "tester": "QA",
    "backend dev": "Backend Dev", "backend": "Backend Dev",
    "frontend dev": "Frontend Dev", "frontend": "Frontend Dev",
}

def _canonical_role(role_text: str) -> str:
    t = _norm(role_text)
    for k, v in _ROLE_SYNONYMS.items():
        if k in t:
            return v
    return role_text.strip().title()

def _parse_team_patch(text: str) -> Optional[Dict[str, Any]]:
    t = _norm(text)
    print(f"  Texto normalizado: {repr(t)}")
    
    def _to_float(num: str) -> float:
        if not num:
            return 1.0
        s = num.strip().lower()
        if s in ("medio", "0.5", "0,5", "media"):
            return 0.5
        try:
            return float(s.replace(",", "."))
        except Exception:
            return 1.0

    ops: List[Dict[str, Any]] = []

    # Formato directo: "Backend Dev x2" o "PM x0.5"
    print(f"  Buscando patrón 'Role x Number'...")
    for m in re.finditer(r"([a-zA-Z][a-zA-Z\s/]*?)\s+x\s*(\d+(?:[.,]\d+)?)", t):
        role, num = m.groups()
        print(f"    ✓ Encontrado: role={repr(role)}, num={repr(num)}")
        ops.append({"op": "set", "role": role.strip(), "count": _to_float(num)})

    if not ops:
        return None
    
    return {"type": "team", "ops": ops}

# Test 1: "/cambiar: QA x2"
print("=" * 60)
print("TEST 1: Simulando comando '/cambiar: QA x2'")
print("=" * 60)

command = "/cambiar: QA x2"
print(f"Comando original: {repr(command)}")

# Extraer argumento
arg = command.split(":", 1)[1].strip()
print(f"Argumento extraído: {repr(arg)}")

# Parsear patch
patch = _parse_team_patch(arg)
print(f"Patch parseado: {patch}")

if patch:
    # Normalizar roles en ops
    print(f"\nNormalizando roles en ops:")
    for op in patch.get("ops", []):
        original = op["role"]
        op["role"] = _canonical_role(op["role"])
        print(f"  {repr(original)} -> {repr(op['role'])}")
    
    print(f"\nPatch final: {patch}")

# Test 2: "/cambiar: Backend Dev x1.5"
print("\n" + "=" * 60)
print("TEST 2: Simulando comando '/cambiar: Backend Dev x1.5'")
print("=" * 60)

command2 = "/cambiar: Backend Dev x1.5"
arg2 = command2.split(":", 1)[1].strip()
patch2 = _parse_team_patch(arg2)
print(f"Patch parseado: {patch2}")

if patch2:
    for op in patch2.get("ops", []):
        original = op["role"]
        op["role"] = _canonical_role(op["role"])
        print(f"  {repr(original)} -> {repr(op['role'])}")
