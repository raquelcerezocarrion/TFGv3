import re
import unicodedata

def _norm(s: str) -> str:
    if s is None:
        return ""
    nk = unicodedata.normalize('NFKD', s.lower())
    return ''.join(c for c in nk if not unicodedata.combining(c)).strip()

# Regex exacta del código
pattern = r"([a-zA-Z][a-zA-Z\s/]*?)\s+x\s*(\d+(?:[.,]\d+)?)"

tests = [
    "QA x2",
    "Backend Dev x1.5",
    "PM x0.5",
    "Security x1",
    "ML Engineer x2",
]

print("Testing la regex del backend:\n")
for test in tests:
    normalized = _norm(test)
    print(f"Original:    {repr(test)}")
    print(f"Normalizado: {repr(normalized)}")
    
    matches = list(re.finditer(pattern, normalized))
    if matches:
        for m in matches:
            role, num = m.groups()
            print(f"  ✓ Match: role={repr(role)}, num={repr(num)}")
    else:
        print(f"  ✗ NO MATCH")
    print()
