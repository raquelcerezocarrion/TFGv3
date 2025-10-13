# TFGv3

## Para arrancar el frontend
### npm run dev

## Generar gráfico de desglose del presupuesto

Se incluye un script sencillo para generar un gráfico de pastel similar al adjunto en `scripts/budget_pie.py`.

- Ejecutar con el Python del entorno virtual del proyecto:

```powershell
C:/Users/HP/Desktop/TFGv3/.venv/Scripts/python.exe scripts/budget_pie.py
```

- El script guarda la imagen `budget_pie.png` en la raíz del proyecto.
- Para personalizar las categorías o porcentajes, edita las listas `labels` y `sizes` dentro de `scripts/budget_pie.py`.

### Vista previa

![Desglose del presupuesto](./budget_pie.png)
# TFGv3

## Para arrancar el backend :
### .\.venv\Scripts\Activate.ps1
### python -m uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000

## Para arrancar el frontend
### npm run dev