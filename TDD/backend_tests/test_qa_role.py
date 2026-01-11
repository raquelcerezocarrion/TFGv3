import unicodedata

def _norm(s: str) -> str:
    if s is None:
        return ""
    nk = unicodedata.normalize('NFKD', s.lower())
    return ''.join(c for c in nk if not unicodedata.combining(c)).strip()

_ROLE_SYNONYMS = {
    "qa": "QA", "quality": "QA", "tester": "QA",
    "backend dev": "Backend Dev", "backend": "Backend Dev",
}

def _canonical_role(role_text: str) -> str:
    t = _norm(role_text)
    print(f"\nBuscando coincidencias para: {repr(role_text)} -> normalizado: {repr(t)}")
    for k, v in _ROLE_SYNONYMS.items():
        match = k in t
        print(f"  {repr(k)} in {repr(t)} = {match} -> retorna {repr(v) if match else 'continúa'}")
        if match:
            return v
    return role_text.strip().title()

# Pruebas
result_qa = _canonical_role('QA')
print(f"\n✓ Resultado para 'QA': {repr(result_qa)}")

result_backend = _canonical_role('Backend Dev')
print(f"✓ Resultado para 'Backend Dev': {repr(result_backend)}")
