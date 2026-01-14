Guía rápida para desplegar en Render
===================================

Opciones soportadas por este repo:
- Deploy directo (Render Web Service, sin Docker): Render instalará dependencias desde `requirements.txt` y ejecutará el comando de inicio.
- Deploy por Docker (Render Docker): Render construye la imagen desde `docker/Dockerfile.backend`.

Cambios aplicados en el repo (mínimos y no alteran la lógica de la app):
- `docker/Dockerfile.backend`: ahora usa `${PORT}` en tiempo de ejecución, elimina `--reload` y ejecuta `uvicorn` con `--workers 4` y `--proxy-headers`.
- `Procfile`: comando de inicio listo para plataformas que lo usen.

Despliegue recomendado (Web Service, más rápido)
------------------------------------------------
1. Conecta tu repositorio a Render (GitHub/GitLab).
2. Crea un nuevo "Web Service".
   - Build Command: dejar vacío o `pip install -r requirements.txt`.
   - Start Command: `uvicorn backend.app:app --host 0.0.0.0 --port $PORT --proxy-headers`
   - Runtime: Python 3.11 (Render detecta automáticamente si no especificas).
3. Variables de entorno importantes:
   - `SECRET_KEY`: cambia el valor por defecto de `backend/core/config.py` (no uses el valor dev en producción).
   - `FRONTEND_ORIGIN`: si quieres restringir CORS al dominio del frontend (ej: `https://mi-front.onrender.com`).
   - `DATABASE_URL`: opcional. Si no la pones, la app usará SQLite local (archivo en disco efímero de la instancia).
4. Desplegar y abrir la URL pública que Render asigna.

Notas y recomendaciones
----------------------
- WebSockets: la app soporta WebSockets; Render Web Services también los soporta. Asegúrate de usar `wss://` si el frontend se sirve por HTTPS.
- Persistencia: la máquina de Render no ofrece almacenamiento persistente entre despliegues. Si necesitas conservar datos (usuarios, chats, propuestas), crea un servicio de Postgres en Render y pon allí su URL en `DATABASE_URL`.
- Seguridad/CORS: el código permite orígenes amplios en desarrollo. Si quieres cerrar CORS en producción, configura `FRONTEND_ORIGIN` y actualiza la configuración en `backend/app.py` si lo deseas (no fue modificado).
- Docker: si prefieres desplegar por Docker, el `docker/Dockerfile.backend` ya respeta `${PORT}` y es apto para producción.

Comandos útiles para probar localmente
-------------------------------------
Construir imagen Docker (opcional):
```bash
docker build -f docker/Dockerfile.backend -t tfg-backend:prod .
docker run -p 8000:8000 -e PORT=8000 tfg-backend:prod
```

Probar con uvicorn localmente (sin Docker):
```bash
pip install -r requirements.txt
uvicorn backend.app:app --host 0.0.0.0 --port 8000 --proxy-headers
```

Si quieres, preparo también un `render.yaml` para infra-as-code o un PR con una pequeña mejora de CORS basada en `FRONTEND_ORIGIN`.
