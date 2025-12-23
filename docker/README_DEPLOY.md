Este README breve explica cómo levantar el proyecto en local con Docker (desarrollo).

Requisitos:
- Docker Desktop (o Docker Engine) instalado y en ejecución
- En Windows, usar PowerShell / WSL2 para mejor rendimiento de I/O

Comandos rápidos:

# Levantar en modo desarrollo (bind-mounts, recarga)
docker compose up --build

# Levantar en background (detached)
docker compose up -d --build

# Reconstruir solo backend y recrear servicio
docker compose build backend
docker compose up -d --force-recreate backend

Notas importantes:
- En este setup `backend` monta el código de `./backend` y el fichero de BD `./backend/memory`.
  Si modificas código localmente, con `uvicorn --reload` los cambios se aplican sin reconstruir la imagen.
- Para producción, se recomienda:
  - Migrar SQLite a Postgres u otra DB cliente/servidor.
  - Hacer builds de frontend y servir estático con un servidor (nginx) o CDN.
  - Evitar bind-mounts y bakear artefactos en la imagen.
