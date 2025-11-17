"""Test del flujo completo: generar propuesta → aceptar → asignar empleados → decir 'sí' → verificar propuestas disponibles en Seguimiento.

Uso:
    python scripts/test_seguimiento_flow.py
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import requests
import json

BASE = 'http://localhost:8000'

"""Test de seguimiento eliminado.

Se mantiene el archivo como placeholder porque la funcionalidad de seguimiento fue removida.
"""
if __name__ == '__main__':
def test_seguimiento_flow():
    print('SKIPPED: seguimiento feature removed')


if __name__ == '__main__':
    test_seguimiento_flow()
    test_seguimiento_flow()
