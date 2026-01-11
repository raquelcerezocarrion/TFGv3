# 🐳 Guía de Ejecución con Docker Desktop

## Prerrequisitos

1. **Docker Desktop instalado y en ejecución**
   - Descargar desde: https://www.docker.com/products/docker-desktop/
   - Asegúrate de que Docker Desktop esté ejecutándose (icono en la bandeja del sistema)

2. **Variables de entorno**
   - Copia el archivo `.env.example` a `.env` en la raíz del proyecto
   - Configura tu `OPENAI_API_KEY` en el archivo `.env`

## 🚀 Comandos para Ejecutar

### Iniciar la aplicación completa

```bash
# Desde la raíz del proyecto (TFGv3/)
cd docker
docker-compose up --build
```

Este comando:
- ✅ Construye las imágenes de backend y frontend
- ✅ Inicia los contenedores
- ✅ Backend disponible en: http://localhost:8000
- ✅ Frontend disponible en: http://localhost:5173

### Ejecutar en segundo plano (detached mode)

```bash
cd docker
docker-compose up -d --build
```

### Ver logs en tiempo real

```bash
# Todos los servicios
docker-compose logs -f

# Solo backend
docker-compose logs -f backend

# Solo frontend
docker-compose logs -f frontend
```

### Detener los contenedores

```bash
cd docker
docker-compose down
```

### Detener y eliminar volúmenes (reinicio completo)

```bash
cd docker
docker-compose down -v
```

### Reconstruir sin caché

```bash
cd docker
docker-compose build --no-cache
docker-compose up
```

## 📋 Verificación

### 1. Verificar que los contenedores están corriendo

Desde Docker Desktop:
- Abre Docker Desktop
- Ve a la pestaña "Containers"
- Deberías ver `tfg-backend` y `tfg-frontend` en estado "Running"

Desde terminal:
```bash
docker ps
```

### 2. Probar el backend

```bash
curl http://localhost:8000/health
```

Deberías recibir:
```json
{"status":"ok"}
```

### 3. Abrir el frontend

Abre tu navegador en: http://localhost:5173

## 🛠️ Comandos Útiles

### Acceder a la terminal del backend

```bash
docker exec -it tfg-backend bash
```

### Acceder a la terminal del frontend

```bash
docker exec -it tfg-frontend sh
```

### Ver uso de recursos

En Docker Desktop:
- Ve a la pestaña "Containers"
- Haz clic en el contenedor
- Verás CPU, memoria y tráfico de red

### Reiniciar un servicio específico

```bash
# Solo backend
docker-compose restart backend

# Solo frontend
docker-compose restart frontend
```

## 🐛 Solución de Problemas

### El puerto 8000 o 5173 ya está en uso

```bash
# Ver qué está usando el puerto
netstat -ano | findstr :8000
netstat -ano | findstr :5173

# Cambiar los puertos en docker-compose.yml:
ports:
  - "8001:8000"  # Para backend
  - "5174:5173"  # Para frontend
```

### Los cambios en el código no se reflejan

- Los volúmenes están montados, así que los cambios deberían reflejarse automáticamente
- Si no funciona, reinicia el contenedor:
  ```bash
  docker-compose restart backend
  docker-compose restart frontend
  ```

### Error de permisos en Windows

Asegúrate de que Docker Desktop tiene acceso a la carpeta del proyecto:
1. Docker Desktop → Settings → Resources → File Sharing
2. Agrega `C:\Users\HP\Desktop\TFGv3`

### Backend no se conecta a la base de datos

La base de datos SQLite se monta desde `../data/app.db`. Asegúrate de que:
```bash
# Verificar que el archivo existe
ls data/app.db

# Si no existe, el backend lo creará automáticamente
```

## 📦 Limpieza Completa

Si necesitas limpiar todo y empezar de cero:

```bash
cd docker

# Detener y eliminar contenedores, redes y volúmenes
docker-compose down -v

# Eliminar imágenes construidas
docker rmi tfg-backend tfg-frontend

# Eliminar imágenes no utilizadas
docker image prune -a
```

## 🎯 Workflow Recomendado

### Desarrollo diario:

1. **Primera vez del día:**
   ```bash
   cd docker
   docker-compose up
   ```

2. **Trabajar normalmente** - los cambios se reflejan automáticamente

3. **Al terminar:**
   ```bash
   docker-compose down
   ```

### Después de cambios en dependencias:

```bash
cd docker
docker-compose down
docker-compose up --build
```

## ✅ Checklist de Inicio Rápido

- [ ] Docker Desktop instalado y corriendo
- [ ] Archivo `.env` configurado con `OPENAI_API_KEY`
- [ ] Terminal abierta en `C:\Users\HP\Desktop\TFGv3\docker`
- [ ] Ejecutar: `docker-compose up --build`
- [ ] Esperar a ver: "Application startup complete"
- [ ] Abrir http://localhost:5173 en el navegador
- [ ] ¡Listo para desarrollar!

## 📞 Comandos de Un Solo Paso

### Iniciar todo:
```bash
cd C:\Users\HP\Desktop\TFGv3\docker && docker-compose up --build
```

### Detener todo:
```bash
cd C:\Users\HP\Desktop\TFGv3\docker && docker-compose down
```

### Ver logs:
```bash
cd C:\Users\HP\Desktop\TFGv3\docker && docker-compose logs -f
```
