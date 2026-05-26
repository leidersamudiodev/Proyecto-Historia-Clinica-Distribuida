# Proyecto-Historia-Clinica-Distribuida
# 🏥 Enterprise Distributed Electronic Health Record (EHR) System
### *Infraestructura Distribuida e Interoperable basada en HL7 FHIR R4, FastAPI y Observabilidad en Tiempo Real*

---

[![Licencia](https://img.shields.io/badge/Licencia-MIT-green.svg)]()
[![FHIR Version](https://img.shields.io/badge/HL7%20FHIR-R4%20(v4.0.1)-blue.svg)](https://hl7.org/fhir/R4/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.95+-009688.svg?style=flat&logo=fastapi&logoColor=white)]()
[![Docker](https://img.shields.io/badge/Docker%20Compose-v2+-2496ED.svg?style=flat&logo=docker&logoColor=white)]()
[![Prometheus](https://img.shields.io/badge/Prometheus-M%C3%A9tricas-E6522C.svg?style=flat&logo=prometheus&logoColor=white)]()
[![Grafana](https://img.shields.io/badge/Grafana-Dashboards-F46800.svg?style=flat&logo=grafana&logoColor=white)]()

Este proyecto representa una implementación de nivel empresarial para un **Sistema de Historia Clínica Distribuida** interoperable. Está diseñado bajo el estándar internacional **HL7 FHIR R4** para garantizar el intercambio seguro y estructurado de datos clínicos, y cuenta con un **Middleware inteligente con tolerancia activa a fallos (Failover)** y un motor asíncrono de consistencia eventual para soportar el ciclo de vida clínico bajo alta disponibilidad.

---

## 🎯 Objetivos de la Arquitectura
*   **Interoperabilidad Semántica**: Adopción estricta de perfiles FHIR R4 (`Patient`, `Encounter`, `Observation`, `Condition`, `MedicationRequest`).
*   **Fragmentación Horizontal (Sharding)**: Distribución eficiente y regionalizada de los datos demográficos y registros clínicos de los pacientes en múltiples bases de datos.
*   **Tolerancia Activa a Fallas**: Enrutamiento asimétrico alternativo en caso de indisponibilidad física de los shards, garantizando cero pérdida de datos.
*   **Consistencia Eventual Automatizada**: Sincronización transparente de transacciones encoladas en memoria en un intervalo máximo de 2 segundos tras la recuperación física de los nodos.
*   **Observabilidad Completa**: Monitorización exhaustiva de latencias de consultas distribuidas, tasas de error y estado de salud de cada microservicio.

---

## 🏗️ Plano de la Arquitectura del Sistema

```
                                  +------------------------------------+
                                  |         CLIENTE / FRONTEND         |
                                  |     (Dashboard Web Interactivo)    |
                                  +-----------------+------------------+
                                                    |  HTTPS / JSON
                                                    v
                                  +------------------------------------+
                                  |    MIDDLEWARE API GATEWAY (FastAPI)|
                                  |    - Autenticación JWT (PyJWT)     |
                                  |    - Enrutador de Shard Geográfico |
                                  |    - Monitor de Latencia en Vívido |
                                  +--------+--------+--------+---------+
                                           |        |        |
         +---------------------------------+        |        +---------------------------------+
         | (Rango Shard 1)                          | (Rango Shard 2)                          | (Rango Shard 3)
         v                                          v                                          v
+------------------+                       +------------------+                       +------------------+
| hapi-fhir-sincelejo                      | hapi-fhir-bogota |                       | hapi-fhir-medellin
|   (Nodo 1)       |                       |   (Nodo 2)       |                       |   (Nodo 3)       |
+--------+---------+                       +--------+---------+                       +--------+---------+
         |                                          |                                          |
         v                                          v                                          v
+------------------+                       +------------------+                       +------------------+
| pg_nodo1 (5433)  |                       | pg_nodo2 (5434)  |                       | pg_nodo3 (5435)  |
| Región Caribe    |                       | Región Andina 1  |                       | Región Andina 2  |
| Rango: 0 a 3.99G |                       | Rango: 4G a 6.99G|                       | Rango: 7G a 9.99G|
+------------------+                       +------------------+                       +------------------+
        ^                                          ^                                          ^
        |                                          |                                          |
        +------------------------------------------+------------------------------------------+
                                                   | Raspado de Métricas (HTTP GET /metrics)
                                                   v
                                       +-----------------------+
                                       |      PROMETHEUS       |
                                       +-----------+-----------+
                                                   | Graficación
                                                   v
                                       +-----------------------+
                                       |   GRAFANA DASHBOARD   |
                                       +-----------------------+
```

---

## 💾 Modelo de Fragmentación (Sharding)

El sistema distribuye la información demográfica (`usuario` / `Patient`) de acuerdo con un esquema de fragmentación horizontal basado en rangos numéricos del campo `documento_id`. El Middleware enruta la escritura e inserción al **Nodo Primario** correspondiente según la siguiente regla matemática:

| Nodo ID | Región de Operación | Rango de Identificación (`documento_id`) | Puerto PostgreSQL | Puerto FHIR Server |
|:---:|---|---|:---:|:---:|
| **`nodo1`** | Sincelejo (Región Caribe) | $0 \le \text{ID} \le 3,999,999,999$ | `5433` | `8081` |
| **`nodo2`** | Bogotá (Región Andina) | $4,000,000,000 \le \text{ID} \le 6,999,999,999$ | `5434` | `8082` |
| **`nodo3`** | Medellín (Región Andina) | $7,000,000,000 \le \text{ID} \le 9,999,999,999$ | `5435` | `8083` |

> [!NOTE]
> Cuando se realiza una consulta de lectura global (ej. listar todas las historias clínicas), el Middleware ejecuta una consulta asíncrona paralela en todos los shards activos y consolida los resultados en memoria de forma transparente para el cliente.

---

## 🛡️ Motor de Resiliencia y Failover Activo

### Flujo de Tolerancia a Fallos
1. **Detección Activa**: Si un nodo de base de datos o servidor FHIR primario no responde en un límite de tiempo programado (`CONNECT_TIMEOUT = 3s`), el Middleware captura la excepción y marca al nodo como `DOWN`.
2. **Redirección Inmediata (Failover)**: La petición de escritura de emergencia se redirige a un nodo secundario que se encuentre `UP`, garantizando que el personal médico no detenga su labor asistencial.
3. **Buffer en Memoria**: El registro fallido se añade a la **Cola de Sincronización** interna del nodo primario caído (`cola_sincronizacion`).
4. **Reconciliación y Autorecuperación (Self-Healing)**:
   * El daemon de fondo (`re-sync-worker`) monitorea cada $2\text{ s}$ la disponibilidad de los nodos caídos.
   * Al detectar la recuperación física del nodo, vacía la cola local insertando los registros acumulados con la instrucción estructurada `INSERT ... ON CONFLICT DO NOTHING`.
   * Registra el tiempo de latencia y el estado final del proceso en el historial clínico central.

---

## 🛠️ Stack Tecnológico Completo

### Capa de Aplicación y Servicios
*   **FastAPI v0.95.2**: API de alto rendimiento con generación automática de OpenAPI (Swagger).
*   **PyJWT v2.8.0**: Generación y decodificación asimétrica de firmas criptográficas JWT.
*   **HAPI FHIR JPAServer (v6.6.0)**: Motor estándar de interoperabilidad médica implementado en Java.
*   **Psycopg2-binary**: Conector PostgreSQL asíncrono optimizado para Python.

### Capa de Datos e Infraestructura
*   **PostgreSQL 15 (Alpine)**: Motor relacional con almacenamiento estructurado para HAPI FHIR schemas.
*   **Docker & Docker Compose**: Contenerización integrada de 10 microservicios independientes.

### Capa de Observabilidad
*   **Prometheus**: Servidor de base de datos temporal encargado de capturar métricas del host y estados de la API.
*   **Grafana**: Herramienta de analítica avanzada con dashboards dinámicos parametrizados.

---

## 🚀 Guía de Despliegue Rápido

### Prerrequisitos de Sistema (Linux / macOS / Windows)
*   **Docker Engine** $\ge$ v20.10.x
*   **Docker Compose** $\ge$ v2.x
*   **Puertos Libres**: `8001`, `8081`, `8082`, `8083`, `5433`, `5434`, `5435`, `9090`, `3000`.

### Paso 1: Levantar los Microservicios
Clone el repositorio en su espacio de trabajo y ejecute el levantamiento orquestado de contenedores en segundo plano:

```bash
docker compose up -d
```

> [!IMPORTANT]
> Los servidores HAPI FHIR Java pueden requerir hasta 60-90 segundos para completar las migraciones iniciales de base de datos en su primer encendido. El sistema utiliza Docker Healthchecks nativos para avisarle cuando todo el stack esté en línea.

### Paso 2: Verificar Salud del Clúster
Valide que todos los contenedores y puertos expuestos estén funcionando:

```bash
docker compose ps
```

Adicionalmente, ejecute el script de verificación automatizado para probar la conectividad de socket físico:

```bash
./verificar-docker.sh
```

---

## 🔌 Direccionamiento y Mapa de Puertos

### 💻 Infraestructura y Microservicios
El entorno de producción simulado expone los siguientes endpoints y paneles de administración de infraestructura:

| Puerto | Servicio / Rol | URL de Acceso / Endpoint | Tipo de Interfaz |
|:---:|---|---|---|
| **`8001`** | Middleware Central & API Gateway | [http://localhost:8001](http://localhost:8001) | Dashboard Principal |
| **`8001`** | Documentación de la API (Swagger UI) | [http://localhost:8001/docs](http://localhost:8001/docs) | OpenAPI Docs |
| **`8081`** | HAPI FHIR Server (Caribe - Sincelejo) | [http://localhost:8081](http://localhost:8081) | Consola Java / Web |
| **`8082`** | HAPI FHIR Server (Andina - Bogotá) | [http://localhost:8082](http://localhost:8082) | Consola Java / Web |
| **`8083`** | HAPI FHIR Server (Andina - Medellín) | [http://localhost:8083](http://localhost:8083) | Consola Java / Web |
| **`3000`** | Servidor de Analítica (Grafana) | [http://localhost:3000](http://localhost:3000) | Dashboard de Observabilidad |
| **`9090`** | Monitor de Métricas (Prometheus) | [http://localhost:9090](http://localhost:9090) | Consola de Prometheus |

### 🏥 Rutas y Vistas del Frontend Clínico
La aplicación web centralizada expone las siguientes interfaces clínicas y administrativas:

| Módulo Clínico | Ruta del Sistema | URL Directa de Acceso | Descripción del Módulo |
|---|---|---|---|
| **Panel de Control** | `/` | [http://localhost:8001/](http://localhost:8001/) | Estado de nodos en vivo, consola SQL distribuida y logs del sistema. |
| **Registro de Paciente** | `/registro-paciente` | [http://localhost:8001/registro-paciente](http://localhost:8001/registro-paciente) | Formulario estructurado de ingreso con 15 campos clínicos obligatorios. |
| **Consulta de Historias** | `/consulta-hc` | [http://localhost:8001/consulta-hc](http://localhost:8001/consulta-hc) | Panel de búsqueda parametrizada de historias clínicas con paginación activa. |
| **Módulo de Triage** | `/modulo-triage` | [http://localhost:8001/modulo-triage](http://localhost:8001/modulo-triage) | Captura de constantes fisiológicas y clasificación de Triage (`Encounter` + `Observation`). |
| **Módulo Médico** | `/modulo-medico` | [http://localhost:8001/modulo-medico](http://localhost:8001/modulo-medico) | Formulación médica y registro de diagnósticos CIE-10 (`Condition` + `MedicationRequest`). |
| **Detalle de Paciente** | `/paciente/{id}` | *Ejemplo:* `http://localhost:8001/paciente/1001` | Vista de consolidación de historia clínica e inspección del payload en formato HL7 FHIR JSON. |
| **Módulo de Reportes** | `/reportes` | [http://localhost:8001/reportes](http://localhost:8001/reportes) | Panel gerencial de analítica con agregación de consultas geográficas distribuidas. |


---

## 🔑 Autenticación OAuth2 / SMART on FHIR

Para garantizar la seguridad de los registros clínicos, los endpoints de escritura (`POST`) están restringidos mediante la validación estricta de tokens Bearer JWT firmados con el algoritmo `HS256`.

### 1. Obtener Token de Acceso
Envíe una petición al endpoint de autenticación con credenciales autorizadas (roles: `admin`, `medico`, `enfermero`):

```bash
curl -X POST http://localhost:8001/api/auth/token \
     -H "Content-Type: application/json" \
     -d '{"username": "medico", "password": "medico123"}'
```

**Respuesta Exitosa (200 OK):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

### 2. Consumir Endpoint FHIR con Token
Agregue la cabecera `Authorization: Bearer <TOKEN>` en cada consulta:

```bash
curl -X POST http://localhost:8001/api/v1/fhir/patient \
     -H "Authorization: Bearer <TU_TOKEN_JWT>" \
     -H "Content-Type: application/json" \
     -d '{
       "documento_id": 1002345678,
       "nombre_completo": "Laura Camila Restrepo",
       "fecha_nacimiento": "1994-08-15",
       "sexo": "F",
       "pais_residencia": "Colombia",
       "municipio_residencia": "Sincelejo"
     }'
```

---

## 🧪 Demostraciones Clínicas de Tolerancia a Fallas

El sistema cuenta con un script interactivo diseñado para demostrar ante auditores académicos o de sistemas cómo funciona la **consistencia eventual** y la **alta disponibilidad (HA)**:

```bash
./demo-failover.sh
```

### ¿Qué hace esta prueba bajo el capó?
1. **Línea de Base**: Verifica que los 3 nodos geográficos estén completamente activos (`UP`).
2. **Caída Controlada**: Apaga intencionalmente el shard primario correspondiente a un rango (ej. apaga `hapi-fhir-sincelejo`).
3. **Escritura Transaccional**: Inserta un paciente nuevo cuyo documento debería ir a Sincelejo. El Middleware captura el fallo del nodo primario, aplica **Failover** y guarda el registro en el nodo secundario (Bogotá o Medellín) de forma temporal, agregando el registro a la cola de pendientes.
4. **Validación del Buffer**: Demuestra que los datos no se perdieron y el Middleware respondió exitosamente.
5. **Autorecuperación**: Reactiva el contenedor apagado.
6. **Reconciliación de Consistencia**: Espera $2\text{ s}$ para que el `re-sync-worker` transfiera los registros pendientes y valide que la base de datos de Sincelejo ahora contenga el registro de forma íntegra.

> [!WARNING]
> El Middleware implementa una **Regla de Quórum Activa** en `POST /api/nodes/{id}/stop`. Si intenta apagar un nodo cuando ya no quedan más nodos activos en el clúster, el sistema rechazará la acción retornando un código `409 Conflict` para prevenir la indisponibilidad total del sistema.

---

## 📊 Observabilidad Avanzada (Prometheus & Grafana)

El sistema genera métricas y telemetría estructurada. Para ver la monitorización:

1. Ingrese a **Grafana**: [http://localhost:3000](http://localhost:3000)
2. Autentíquese con: **Usuario**: `admin` | **Contraseña**: `admin123`
3. Visualice los dashboards interactivos preconfigurados:
   - **Tasa de Éxito de Peticiones** (Requests throughput y códigos HTTP 2xx, 4xx, 5xx).
   - **Tiempo de Respuesta por Shard** (Latencia media en milisegundos).
   - **Estado Físico de Contenedores** (Estado de salud de HAPI FHIR).
   - **Métricas de Sincronización** (Eventos procesados por el Sync Worker).

---

## 📁 Árbol del Directorio de Proyecto

```
historia-clinica-distribuida/
├── app.py                      # Gateway FastAPI y vistas HTML
├── middleware.py               # Algoritmo de Sharding, Failover y Re-Sync Worker
├── docker-compose.yml          # Orquestador de contenedores
├── requirements.txt            # Dependencias de Python
├── test-mvp-fhir.sh            # Script automatizado de pruebas E2E
├── demo-failover.sh            # Script interactivo de simulación de fallas
├── verificar-docker.sh         # Script utilitario de diagnóstico
├── templates/                  # Vistas HTML (Triage, Médico, Registro, Detalle)
│   ├── index.html              # Dashboard Principal
│   ├── registro-paciente.html  # Registro de 15 Campos
│   ├── consulta-hc.html        # Módulo de Búsqueda y Paginación
│   └── paciente-detalle.html   # Visualización detallada de la HC
├── static/                     # Archivos de estilo CSS y JS reactivo
│   ├── style.css
│   └── script.js
└── monitoring/                 # Archivos de Observabilidad
    ├── prometheus.yml          # Configuración del raspador de métricas
    └── grafana/
        ├── datasources/        # Aprovisionamiento del motor Prometheus
        └── dashboards/         # Dashboards parametrizados en JSON
```

---

## 🛑 Detener el Ecosistema

Para liberar los puertos físicos del host, detenga el clúster usando Docker:

```bash
docker compose down
```

Si desea realizar un restablecimiento total (borrando volúmenes lógicos y bases de datos para iniciar de cero):

```bash
docker compose down -v
```

---
**Desarrollado para demostración de arquitecturas de bases de datos altamente integradas, resilientes y conformes al estándar HL7 FHIR.**
