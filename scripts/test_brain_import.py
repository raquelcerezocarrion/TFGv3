import sys
sys.path.insert(0, '.')
from backend.engine import brain

print(f"save_proposal: {brain.save_proposal}")
print(f"callable: {callable(brain.save_proposal)}")

# Try calling it
result = brain.save_proposal('test', 'test', {})
print(f"Result: {result}")
