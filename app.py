# app.py - Sistema de Historia Clínica Distribuida con FHIR
from fastapi import FastAPI, HTTPException, Depends, Security
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import os
import sys
import middleware
import psycopg2
import logging
import json
import jwt
from datetime import datetime, timedelta, timezone
from typing import Optional, List

# Configurar logging estructurado
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
logger = logging.getLogger(__name__)

from backend.fhir_app.models.patient_model import PatientIdentificationData
from backend.fhir_app.models.clinical_models import TriageData, ConsultationData
from backend.fhir_app.transformers.fhir_transformer import FHIRTransformer
from backend.fhir_app.services.fhir_service import FHIRService

# ============================================================================
# SEGURIDAD: JWT real con PyJWT (firma HS256 + expiración)
# ============================================================================
JWT_SECRET = os.getenv("JWT_SECRET", "hc-fhir-jwt-secret-distribuido-2024")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = 60
JWT_REQUIRE_AUTH = os.getenv("JWT_REQUIRE_AUTH", "true").lower() == "true"
security = HTTPBearer(auto_error=False)

_system_logs: List[dict] = []  # log en memoria

def _log_event(tipo: str, msg: str):
    entry = {"type": tipo, "ts": datetime.now().isoformat(), "msg": msg}
    _system_logs.append(entry)
    if len(_system_logs) > 200:
        _system_logs.pop(0)
    logger.info(f"[{tipo.upper()}] {msg}")

def _generar_jwt(username: str, role: str) -> str:
    """Genera un JWT firmado con expiración y scopes SMART on FHIR."""
    payload = {
        "sub": username,
        "role": role,
        "scope": "patient/*.read patient/*.write fhir/read fhir/write",
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def verificar_token(credentials: HTTPAuthorizationCredentials = Security(security)):
    """Verifica el Bearer JWT. Retorna payload si válido, None si no hay token (modo demo)."""
    if credentials is None:
        return None  # modo demo sin autenticación
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado. Solicite uno nuevo en /api/auth/token")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token JWT inválido")


def verificar_token_requerido(credentials: HTTPAuthorizationCredentials = Security(security)):
    """
    Verifica el Bearer JWT — REQUERIDO para endpoints de escritura FHIR.
    Implementa OAuth2 / SMART on FHIR con scopes.
    Sin token válido retorna 401 Unauthorized.
    """
    if not JWT_REQUIRE_AUTH:
        return {"sub": "demo", "role": "admin", "scope": "patient/*.read patient/*.write fhir/read fhir/write"}
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Autenticación requerida. Obtenga un token en POST /api/auth/token",
            headers={"WWW-Authenticate": "Bearer scope=\"patient/*.write fhir/write\""}
        )
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado. Solicite uno nuevo en /api/auth/token")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token JWT inválido")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Cargar HTML de FIRH al iniciar
FIRH_HTML = None
_firh_path = os.path.join(BASE_DIR, "templates", "firh.html")
if os.path.isfile(_firh_path):
    with open(_firh_path, "r", encoding="utf-8") as _f:
        FIRH_HTML = _f.read()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuración de nodos (usar nombres de contenedores en Docker)
USE_DOCKER_NAMES = os.getenv("USE_DOCKER_NAMES", "false").lower() == "true"

if USE_DOCKER_NAMES:
    NODES_CONFIG = [
        {"id": "pg_nodo1", "host": "pg_nodo1", "port": 5432, "display_port": "5433"},
        {"id": "pg_nodo2", "host": "pg_nodo2", "port": 5432, "display_port": "5434"},
        {"id": "pg_nodo3", "host": "pg_nodo3", "port": 5432, "display_port": "5435"},
    ]
else:
    NODES_CONFIG = [
        {"id": "pg_nodo1", "host": "localhost", "port": 5433, "display_port": "5433"},
        {"id": "pg_nodo2", "host": "localhost", "port": 5434, "display_port": "5434"},
        {"id": "pg_nodo3", "host": "localhost", "port": 5435, "display_port": "5435"},
    ]


@app.get("/", response_class=HTMLResponse)
async def read_root():
    with open(os.path.join(BASE_DIR, "templates", "index.html"), "r", encoding="utf-8") as f:
        return f.read()


@app.get("/api/health")
async def health():
    _log_event("info", "Health check solicitado")
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "nodos": "Sincelejo (5433), Bogotá (5434), Medellín (5435)",
        "fhir": "http://localhost:8080/fhir",
        "monitoring": "http://localhost:3000 (Grafana)"
    }


@app.get("/hc", response_class=HTMLResponse)
@app.get("/hc/", response_class=HTMLResponse)
@app.get("/firh", response_class=HTMLResponse)
@app.get("/firh/", response_class=HTMLResponse)
@app.get("/carga-hc", response_class=HTMLResponse)
@app.get("/carga-hc/", response_class=HTMLResponse)
async def firh_page():
    if FIRH_HTML is None:
        raise HTTPException(status_code=500, detail="Plantilla firh.html no encontrada")
    return HTMLResponse(content=FIRH_HTML)


@app.get("/api/nodes")
async def get_nodes():
    """Obtiene el estado real de los nodos FHIR y de bases de datos PostgreSQL"""
    import httpx
    fhir_nodes = [
        {"id": "nodo1", "nombre": "Sincelejo", "container": "hapi-fhir-sincelejo", "url": "http://hapi-fhir-sincelejo:8080/fhir/metadata"},
        {"id": "nodo2", "nombre": "Bogotá",    "container": "hapi-fhir-bogota",    "url": "http://hapi-fhir-bogota:8080/fhir/metadata"},
        {"id": "nodo3", "nombre": "Medellín",  "container": "hapi-fhir-medellin",  "url": "http://hapi-fhir-medellin:8080/fhir/metadata"},
    ]
    db_nodes = [
        {"id": "db_nodo1", "nombre": "DB Sincelejo", "container": "pg_nodo1", "port": 5433},
        {"id": "db_nodo2", "nombre": "DB Bogotá",    "container": "pg_nodo2", "port": 5434},
        {"id": "db_nodo3", "nombre": "DB Medellín",  "container": "pg_nodo3", "port": 5435},
    ]

    docker_transport = httpx.AsyncHTTPTransport(uds="/var/run/docker.sock")

    async with httpx.AsyncClient(timeout=2.0) as fhir_client, \
               httpx.AsyncClient(transport=docker_transport, timeout=2.0) as docker_client:
        
        # 1. Procesar nodos FHIR
        fhir_results = []
        for node in fhir_nodes:
            status = "exited"
            try:
                r = await fhir_client.get(node["url"], headers={"Accept": "application/fhir+json"})
                if r.status_code == 200:
                    status = "running"
                else:
                    dr = await docker_client.get(f"http://localhost/containers/{node['container']}/json")
                    if dr.status_code == 200:
                        state = dr.json().get("State", {})
                        if state.get("Running"):
                            status = "starting"
            except Exception:
                try:
                    dr = await docker_client.get(f"http://localhost/containers/{node['container']}/json")
                    if dr.status_code == 200:
                        state = dr.json().get("State", {})
                        if state.get("Running"):
                            status = "starting"
                except Exception:
                    status = "exited"
            fhir_results.append({"id": node["id"], "nombre": node["nombre"], "container": node["container"], "port": 8080, "status": status})

        # 2. Procesar nodos DB
        db_results = []
        for node in db_nodes:
            status = "exited"
            try:
                dr = await docker_client.get(f"http://localhost/containers/{node['container']}/json")
                if dr.status_code == 200:
                    state = dr.json().get("State", {})
                    if state.get("Running"):
                        status = "running"
            except Exception:
                status = "exited"
            db_results.append({"id": node["id"], "nombre": node["nombre"], "container": node["container"], "port": node["port"], "status": status})

    return {"fhir": fhir_results, "databases": db_results}


@app.get("/api/nodes/geo")
async def get_nodes_geo():
    """Nodos con información geográfica completa para el dashboard de reportes"""
    import httpx
    import asyncio
    from backend.fhir_app.services.fhir_service import NODE_URLS

    # Definición fija de nodos geográficos
    nodos_base = [
        {"id": "nodo1", "ciudad": "Sincelejo", "region": "Caribe",  "descripcion": "Caribe · nodo1"},
        {"id": "nodo2", "ciudad": "Bogotá",    "region": "Andina",  "descripcion": "Andina · nodo2"},
        {"id": "nodo3", "ciudad": "Medellín",  "region": "Andina",  "descripcion": "Andina · nodo3"},
    ]

    async def fetch_node_stats(nodo_id, url):
        stats = {"total_usuarios": 0, "total_atenciones": 0, "total_diagnosticos": 0, "online": False}
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                # Verificar si el nodo responde
                rm = await client.get(f"{url}/metadata", headers={"Accept": "application/fhir+json"})
                if rm.status_code != 200:
                    return nodo_id, stats
                stats["online"] = True

                r1 = await client.get(f"{url}/Patient?_count=0", headers={"Accept": "application/fhir+json"})
                if r1.status_code == 200: stats["total_usuarios"] = r1.json().get("total", 0)
                r2 = await client.get(f"{url}/Encounter?_count=0", headers={"Accept": "application/fhir+json"})
                if r2.status_code == 200: stats["total_atenciones"] = r2.json().get("total", 0)
                r3 = await client.get(f"{url}/Condition?_count=0", headers={"Accept": "application/fhir+json"})
                if r3.status_code == 200: stats["total_diagnosticos"] = r3.json().get("total", 0)
        except Exception:
            stats["online"] = False
        return nodo_id, stats

    try:
        tasks = [fetch_node_stats(nid, url) for nid, url in NODE_URLS.items()]
        results = await asyncio.gather(*tasks)
        stats_map = {nid: s for nid, s in results}

        nodos_result = []
        for n in nodos_base:
            s = stats_map.get(n["id"], {})
            nodos_result.append({
                **n,
                "status": "running" if s.get("online") else "exited",
                "activo": s.get("online", False),
                "total_usuarios":    s.get("total_usuarios", 0),
                "total_atenciones":  s.get("total_atenciones", 0),
                "total_diagnosticos": s.get("total_diagnosticos", 0),
            })
        return nodos_result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/nodes/{node_id}/{action}")
async def control_node(node_id: str, action: str):
    """
    Controla contenedores Docker a través del socket de Docker montado.
    Sirve para apagar los servidores FHIR y demostrar failover desde el UI.
    ✅ Regla de Alta Disponibilidad: siempre debe quedar al menos 1 nodo FHIR activo.
    """
    import httpx

    container_map = {
        "nodo1": "hapi-fhir-sincelejo",
        "nodo2": "hapi-fhir-bogota",
        "nodo3": "hapi-fhir-medellin",
        "db_nodo1": "pg_nodo1",
        "db_nodo2": "pg_nodo2",
        "db_nodo3": "pg_nodo3"
    }
    fhir_urls = {
        "nodo1": "http://hapi-fhir-sincelejo:8080/fhir/metadata",
        "nodo2": "http://hapi-fhir-bogota:8080/fhir/metadata",
        "nodo3": "http://hapi-fhir-medellin:8080/fhir/metadata",
    }

    if node_id not in container_map:
        raise HTTPException(status_code=400, detail="Nodo no válido")

    if action not in ["start", "stop", "restart"]:
        raise HTTPException(status_code=400, detail="Acción no válida")

    # ─── REGLA DE QUÓRUM SOLO PARA NODOS FHIR ───
    if action == "stop" and not node_id.startswith("db_"):
        nodos_vivos = 0
        async with httpx.AsyncClient(timeout=2.0) as health_client:
            for nid, url in fhir_urls.items():
                try:
                    r = await health_client.get(url, headers={"Accept": "application/fhir+json"})
                    if r.status_code == 200:
                        nodos_vivos += 1
                except Exception:
                    pass

        if nodos_vivos <= 1:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"⚠️ No se puede apagar {node_id.upper()}: "
                    f"es el único nodo FHIR activo. "
                    f"El sistema de Alta Disponibilidad requiere al menos 1 nodo en línea."
                )
            )
        _log_event("warn", f"[FAILOVER] Nodo {node_id} detenido por operador. Nodos restantes: {nodos_vivos - 1}")

    container_name = container_map[node_id]

    try:
        transport = httpx.AsyncHTTPTransport(uds="/var/run/docker.sock")
        async with httpx.AsyncClient(transport=transport, timeout=10.0) as client:
            url = f"http://localhost/containers/{container_name}/{action}"
            r = await client.post(url)
            if r.status_code in (204, 304):
                if action == "stop":     accion_str = "detenido 🔴"
                elif action == "start":  accion_str = "iniciado 🟢"
                else:                    accion_str = "reiniciado 🔄"
                return {"success": True, "message": f"Nodo {node_id} ({container_name}) {accion_str} exitosamente"}
            else:
                raise HTTPException(status_code=500, detail=f"Error Docker: {r.text}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error conectando a Docker sock: {str(e)}")


class QueryRequest(BaseModel):
    query: str


@app.post("/api/execute-query")
async def execute_query(request: QueryRequest):
    try:
        resultado = middleware.ejecutar_query_en_todos_los_nodos(request.query)
        return resultado
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ENDPOINTS FHIR - MVP
# ============================================================================

# Inicializar servicio FHIR
fhir_service = FHIRService()

@app.get("/registro-paciente", response_class=HTMLResponse)
@app.get("/registro-paciente/", response_class=HTMLResponse)
async def registro_paciente_page():
    """Sirve la SPA para el registro de pacientes"""
    try:
        with open(os.path.join(BASE_DIR, "templates", "index.html"), "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="SPA Shell no encontrada")


@app.get("/api/v1/bd/replication-status")
async def get_replication_status():
    """Estado del sistema de distribución: sharding, consistencia eventual y failover"""
    try:
        return middleware.get_replication_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/failover-logs")
async def get_failover_logs():
    """Retorna el historial de logs de failover de BD y consistencia eventual del middleware"""
    try:
        return {
            "failover_logs": middleware._failover_history,
            "sync_logs": middleware._sync_history
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/fhir/patient")
async def create_fhir_patient(data: PatientIdentificationData, token=Depends(verificar_token_requerido)):
    """
    Crea un paciente en HAPI FHIR Server
    
    Recibe los 15 campos de identificación y los transforma a recurso FHIR Patient
    """
    try:
        # 1. Transformar datos a recurso FHIR Patient
        patient_resource = FHIRTransformer.to_fhir_patient(data.dict())
        
        # 2. Enviar a HAPI FHIR Server
        result = await fhir_service.create_patient(patient_resource)
        
        # 3. Extraer ID del paciente creado
        patient_id = result.get("id")
        
        return {
            "success": True,
            "message": "Paciente creado exitosamente en HAPI FHIR",
            "patient_id": patient_id,
            "fhir_resource": result
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al crear paciente: {str(e)}"
        )


@app.get("/api/v1/fhir/patient/{patient_id}")
async def get_fhir_patient(patient_id: str):
    """Obtiene un paciente por ID desde HAPI FHIR"""
    try:
        patient = await fhir_service.get_patient(patient_id)
        
        if patient is None:
            raise HTTPException(status_code=404, detail="Paciente no encontrado")
        
        return patient
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al obtener paciente: {str(e)}"
        )


@app.get("/api/v1/fhir/patient/search/{identifier}")
async def search_fhir_patient(identifier: str):
    """Busca pacientes por número de documento"""
    try:
        results = await fhir_service.search_patient_by_identifier(identifier)
        return results
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al buscar paciente: {str(e)}"
        )


@app.get("/api/v1/fhir/health")
async def fhir_server_health():
    """Verifica el estado de las 3 instancias HAPI FHIR"""
    try:
        result = await fhir_service.check_server_health()
        total_ok = result.get("total_operativos", 0)
        status = "ok" if total_ok == 3 else ("degraded" if total_ok > 0 else "error")
        return {"status": status, "nodos_fhir": result}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Error verificando HAPI FHIR: {str(e)}")


@app.get("/api/v1/fhir/stats/nodos")
async def get_fhir_stats_por_nodo():
    """Estadísticas de recursos FHIR desglosadas por los 3 nodos geográficos"""
    try:
        return await fhir_service.get_stats_by_nodo()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/fhir/patients/sync-status")
async def get_patients_sync_status(page: int = 1, size: int = 50):
    """
    Devuelve todos los pacientes en la red y su estado de sincronización / réplica
    en Sincelejo, Bogotá y Medellín.
    """
    try:
        # 1. Obtener todos los pacientes usando list_all_patients
        result = await fhir_service.list_all_patients(page=page, size=size)
        entries = result.get("entry", [])
        
        patients_status = []
        import httpx
        
        # Mapear IDs únicos de pacientes
        seen_ids = set()
        unique_patients = []
        for entry in entries:
            res = entry.get("resource", {})
            pid = res.get("id")
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                unique_patients.append(res)
        
        # Para cada paciente único, verificar presencia en todos los nodos
        async with httpx.AsyncClient(timeout=3.0) as client:
            for patient in unique_patients:
                pid = patient["id"]
                name = patient.get("name", [{}])[0].get("text", "Sin nombre")
                identifier = patient.get("identifier", [{}])[0].get("value", "N/A")
                
                # Verificar en los 3 nodos
                presencia = {}
                for n_id, base_url in fhir_service.NODE_URLS.items():
                    url = f"{base_url}/Patient/{pid}"
                    try:
                        r = await client.get(url, headers=fhir_service.headers)
                        presencia[n_id] = r.status_code == 200
                    except Exception:
                        presencia[n_id] = False
                        
                # Determinar estado de sincronización global
                all_synced = all(presencia.values())
                
                patients_status.append({
                    "id": pid,
                    "documento": identifier,
                    "nombre": name,
                    "presencia": presencia,
                    "sincronizado": all_synced
                })
                
        return {
            "success": True,
            "total": len(patients_status),
            "patients": patients_status
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/fhir/patient/{patient_id}/sync")
async def sync_patient_to_all_nodes(patient_id: str, token=Depends(verificar_token_requerido)):
    """
    Sincroniza/replica el recurso del paciente de su nodo de origen/actual hacia todos los otros nodos.
    """
    try:
        # 1. Buscar al paciente en todos los nodos
        patient = await fhir_service.get_patient(patient_id)
        if not patient:
            raise HTTPException(status_code=404, detail="Paciente no encontrado en ningún nodo")
        
        # 2. Hacer PUT del mismo recurso en todos los nodos
        import json as _json
        patient_json = _json.dumps(patient)
        
        sync_results = {}
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            for n_id, base_url in fhir_service.NODE_URLS.items():
                put_url = f"{base_url}/Patient/{patient_id}"
                try:
                    r = await client.put(put_url, content=patient_json, headers=fhir_service.headers)
                    if r.status_code in (200, 201):
                        sync_results[n_id] = {"status": "ok", "message": "Sincronizado con éxito"}
                        _log_event("ok", f"Paciente {patient_id} sincronizado en {n_id}")
                    else:
                        sync_results[n_id] = {"status": "error", "message": f"HTTP {r.status_code}"}
                except Exception as e:
                    sync_results[n_id] = {"status": "error", "message": str(e)}
                    
        return {
            "success": True,
            "patient_id": patient_id,
            "results": sync_results
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/consulta-hc", response_class=HTMLResponse)
@app.get("/consulta-hc/", response_class=HTMLResponse)
async def consulta_hc_page():
    """Sirve la página de consulta de historias clínicas unificada en la SPA"""
    try:
        with open(os.path.join(BASE_DIR, "templates", "index.html"), "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="SPA Shell no encontrada")


@app.get("/api/v1/fhir/patients")
async def list_patients(page: int = 1, size: int = 10):
    """
    Lista todos los pacientes con paginación
    
    Query params:
    - page: Número de página (default: 1)
    - size: Tamaño de página (default: 10)
    """
    try:
        # Buscar todos los pacientes usando fhir_service
        bundle = await fhir_service.list_all_patients(page, size)
        
        # Extraer pacientes del bundle
        patients = []
        if bundle and bundle.get("entry"):
            patients = [entry["resource"] for entry in bundle["entry"]]
        
        total = bundle.get("total", 0) if bundle else 0
        total_pages = (total + size - 1) // size if total > 0 else 1
        
        return {
            "patients": patients,
            "total": total,
            "page": page,
            "size": size,
            "total_pages": total_pages
        }
            
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al listar pacientes: {str(e)}"
        )


@app.get("/api/v1/fhir/patients/search")
async def search_patients_query(q: str):
    """
    Busca pacientes por nombre o documento
    
    Query params:
    - q: Término de búsqueda
    """
    try:
        # Buscar pacientes usando fhir_service (busca por ID o nombre en todos los nodos)
        bundle = await fhir_service.search_patients_general(q)
        
        patients = []
        if bundle and bundle.get("entry"):
            patients = [entry["resource"] for entry in bundle["entry"]]
        
        return {
            "patients": patients,
            "total": len(patients),
            "query": q
        }
            
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error en la búsqueda: {str(e)}"
        )


@app.get("/paciente/{patient_id}", response_class=HTMLResponse)
async def patient_detail_page(patient_id: str):
    """Página de detalle de un paciente - Carga la SPA unificada"""
    try:
        # Verificar que el paciente exista
        patient = await fhir_service.get_patient(patient_id)
        if patient is None:
            raise HTTPException(status_code=404, detail="Paciente no encontrado")
            
        with open(os.path.join(BASE_DIR, "templates", "index.html"), "r", encoding="utf-8") as f:
            return f.read()
    except HTTPException:
        raise
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="SPA Shell no encontrada")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/fhir/triage")
async def create_triage(data: TriageData, token=Depends(verificar_token_requerido)):
    try:
        # Determinar nodo por documento del paciente enviado explícitamente en el payload
        from backend.fhir_app.services.fhir_service import _get_nodo_por_documento
        nodo = _get_nodo_por_documento(data.documento)

        # 1. Crear Encounter FHIR en el nodo correcto
        encounter_resource = FHIRTransformer.to_fhir_encounter(data.dict(), data.patientId)
        encounter_result = await fhir_service.create_encounter(encounter_resource, nodo=nodo)
        encounter_id = encounter_result.get("id")

        # 2. Crear Observation (Signos Vitales) vinculada al Encounter
        observation_resource = FHIRTransformer.to_fhir_observation(data.dict(), data.patientId, encounter_id)
        observation_result = await fhir_service.create_observation(observation_resource, nodo=nodo)

        _log_event("ok", f"Triage creado en nodo {nodo} — Encounter {encounter_id}")
        return {
            "success": True,
            "message": f"Triage registrado en HAPI FHIR ({nodo})",
            "nodo": nodo,
            "encounter_id": encounter_id,
            "observation_id": observation_result.get("id")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al registrar triage: {str(e)}")


@app.post("/api/v1/fhir/consultation")
async def create_consultation(data: ConsultationData, token=Depends(verificar_token_requerido)):
    try:
        # Determinar nodo por documento del paciente enviado explícitamente en el payload
        from backend.fhir_app.services.fhir_service import _get_nodo_por_documento
        nodo = _get_nodo_por_documento(data.documento)

        # 1. Diagnóstico Principal
        condition_resource = FHIRTransformer.to_fhir_condition(
            data.diagnosticoEgreso.dict(), data.patientId, data.encounterId, data.medicoResponsable
        )
        condition_result = await fhir_service.create_condition(condition_resource, nodo=nodo)

        # Diagnósticos Relacionados
        related_results = []
        if data.diagnosticoRel1:
            rel1 = FHIRTransformer.to_fhir_condition(
                data.diagnosticoRel1.dict(), data.patientId, data.encounterId, data.medicoResponsable
            )
            res1 = await fhir_service.create_condition(rel1, nodo=nodo)
            related_results.append(res1.get("id"))

        if data.diagnosticoRel2:
            rel2 = FHIRTransformer.to_fhir_condition(
                data.diagnosticoRel2.dict(), data.patientId, data.encounterId, data.medicoResponsable
            )
            res2 = await fhir_service.create_condition(rel2, nodo=nodo)
            related_results.append(res2.get("id"))

        # 2. Medicamentos
        medication_results = []
        for med in data.medicamentos:
            med_resource = FHIRTransformer.to_fhir_medication_request(
                med.dict(), data.patientId, data.encounterId
            )
            med_result = await fhir_service.create_medication_request(med_resource, nodo=nodo)
            medication_results.append(med_result.get("id"))

        _log_event("ok", f"Consulta médica registrada en nodo {nodo} — Condition {condition_result.get('id')}")
        return {
            "success": True,
            "message": f"Consulta médica registrada en HAPI FHIR ({nodo})",
            "nodo": nodo,
            "condition_id": condition_result.get("id"),
            "related_conditions": related_results,
            "medications": medication_results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al registrar consulta médica: {str(e)}")


@app.get("/api/v1/fhir/patient/{patient_id}/record")
async def get_patient_clinical_record(patient_id: str, doc: str = None):
    try:
        record = await fhir_service.get_patient_clinical_record(patient_id, doc)
        return record
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener historia clínica: {str(e)}")

@app.delete("/api/v1/fhir/clear-database")
async def clear_database(token=Depends(verificar_token_requerido)):
    try:
        result = await fhir_service.clear_all_data()
        _log_event("ok", f"Se ha vaciado la base de datos de todos los nodos.")
        return {"success": True, "message": "Bases de datos limpiadas", "details": result["details"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al limpiar base de datos: {str(e)}")



# ============================================================================
# ENDPOINTS FIRH ORIGINALES
# ============================================================================

FIRH_CAMPOS = {
    "usuario": [
        {"nombre": "documento_id", "tipo": "number", "etiqueta": "Documento ID", "requerido": True, "pk": True},
        {"nombre": "nombre_completo", "tipo": "text", "etiqueta": "Nombre completo", "requerido": True},
        {"nombre": "pais_nacionalidad", "tipo": "text", "etiqueta": "País nacionalidad"},
        {"nombre": "fecha_nacimiento", "tipo": "date", "etiqueta": "Fecha nacimiento"},
        {"nombre": "edad", "tipo": "number", "etiqueta": "Edad"},
        {"nombre": "sexo", "tipo": "text", "etiqueta": "Sexo"},
        {"nombre": "genero", "tipo": "text", "etiqueta": "Género"},
        {"nombre": "ocupacion", "tipo": "text", "etiqueta": "Ocupación"},
        {"nombre": "voluntad_anticipada", "tipo": "boolean", "etiqueta": "Voluntad anticipada"},
        {"nombre": "categoria_discapacidad", "tipo": "text", "etiqueta": "Categoría discapacidad"},
        {"nombre": "pais_residencia", "tipo": "text", "etiqueta": "País residencia"},
        {"nombre": "municipio_residencia", "tipo": "text", "etiqueta": "Municipio residencia"},
        {"nombre": "etnia", "tipo": "text", "etiqueta": "Etnia"},
        {"nombre": "comunidad_etnica", "tipo": "text", "etiqueta": "Comunidad étnica"},
        {"nombre": "zona_residencia", "tipo": "text", "etiqueta": "Zona residencia"},
    ],
    "atencion": [
        {"nombre": "documento_id", "tipo": "number", "etiqueta": "Documento ID (paciente)", "requerido": True},
        {"nombre": "entidad_salud", "tipo": "text", "etiqueta": "Entidad salud"},
        {"nombre": "fecha_ingreso", "tipo": "datetime-local", "etiqueta": "Fecha ingreso"},
        {"nombre": "modalidad_entrega", "tipo": "text", "etiqueta": "Modalidad entrega"},
        {"nombre": "entorno_atencion", "tipo": "text", "etiqueta": "Entorno atención"},
        {"nombre": "via_ingreso", "tipo": "text", "etiqueta": "Vía ingreso"},
        {"nombre": "causa_atencion", "tipo": "textarea", "etiqueta": "Causa atención"},
        {"nombre": "fecha_triage", "tipo": "datetime-local", "etiqueta": "Fecha triage"},
        {"nombre": "clasificacion_triage", "tipo": "text", "etiqueta": "Clasificación triage"},
    ],
    "tecnologia_salud": [
        {"nombre": "documento_id", "tipo": "number", "etiqueta": "Documento ID (para enrutar)", "requerido": True},
        {"nombre": "tecnologia_id", "tipo": "text", "etiqueta": "UUID tecnología", "requerido": True},
        {"nombre": "atencion_id", "tipo": "number", "etiqueta": "Atención ID", "requerido": True},
        {"nombre": "descripcion_medicamento", "tipo": "text", "etiqueta": "Descripción medicamento"},
        {"nombre": "dosis", "tipo": "text", "etiqueta": "Dosis"},
        {"nombre": "via_administracion", "tipo": "text", "etiqueta": "Vía administración"},
        {"nombre": "frecuencia", "tipo": "text", "etiqueta": "Frecuencia"},
        {"nombre": "dias_tratamiento", "tipo": "number", "etiqueta": "Días tratamiento"},
        {"nombre": "unidades_aplicadas", "tipo": "number", "etiqueta": "Unidades aplicadas"},
        {"nombre": "id_personal_salud", "tipo": "text", "etiqueta": "UUID profesional"},
        {"nombre": "finalidad_tecnologia", "tipo": "text", "etiqueta": "Finalidad tecnología"},
    ],
    "diagnostico": [
        {"nombre": "documento_id", "tipo": "number", "etiqueta": "Documento ID (para enrutar)", "requerido": True},
        {"nombre": "atencion_id", "tipo": "number", "etiqueta": "Atención ID", "requerido": True},
        {"nombre": "tipo_diagnostico_ingreso", "tipo": "text", "etiqueta": "Tipo diagnóstico ingreso"},
        {"nombre": "diagnostico_ingreso", "tipo": "text", "etiqueta": "Diagnóstico ingreso"},
        {"nombre": "tipo_diagnostico_egreso", "tipo": "text", "etiqueta": "Tipo diagnóstico egreso"},
        {"nombre": "diagnostico_egreso", "tipo": "text", "etiqueta": "Diagnóstico egreso"},
        {"nombre": "diagnostico_rel1", "tipo": "text", "etiqueta": "Diagnóstico rel 1"},
        {"nombre": "diagnostico_rel2", "tipo": "text", "etiqueta": "Diagnóstico rel 2"},
        {"nombre": "diagnostico_rel3", "tipo": "text", "etiqueta": "Diagnóstico rel 3"},
    ],
    "egreso": [
        {"nombre": "documento_id", "tipo": "number", "etiqueta": "Documento ID (para enrutar)", "requerido": True},
        {"nombre": "atencion_id", "tipo": "number", "etiqueta": "Atención ID", "requerido": True},
        {"nombre": "fecha_salida", "tipo": "datetime-local", "etiqueta": "Fecha salida"},
        {"nombre": "condicion_salida", "tipo": "text", "etiqueta": "Condición salida"},
        {"nombre": "diagnostico_muerte", "tipo": "text", "etiqueta": "Diagnóstico muerte"},
        {"nombre": "codigo_prestador", "tipo": "text", "etiqueta": "Código prestador"},
        {"nombre": "tipo_incapacidad", "tipo": "text", "etiqueta": "Tipo incapacidad"},
        {"nombre": "dias_incapacidad", "tipo": "number", "etiqueta": "Días incapacidad"},
        {"nombre": "dias_lic_maternidad", "tipo": "number", "etiqueta": "Días lic. maternidad"},
        {"nombre": "alergias", "tipo": "textarea", "etiqueta": "Alergias"},
        {"nombre": "antecedente_familiar", "tipo": "textarea", "etiqueta": "Antecedente familiar"},
        {"nombre": "riesgos_ocupacionales", "tipo": "textarea", "etiqueta": "Riesgos ocupacionales"},
        {"nombre": "responsable_egreso", "tipo": "text", "etiqueta": "Responsable egreso"},
    ],
    "profesional_salud": [
        {"nombre": "id_personal_salud", "tipo": "text", "etiqueta": "UUID profesional", "requerido": True},
        {"nombre": "nombre", "tipo": "text", "etiqueta": "Nombre", "requerido": True},
        {"nombre": "especialidad", "tipo": "text", "etiqueta": "Especialidad"},
    ],
}


@app.get("/api/firh/campos")
async def firh_campos():
    return FIRH_CAMPOS


class FirhCargarBody(BaseModel):
    tabla: str
    datos: dict


@app.post("/api/firh/cargar")
async def firh_cargar(body: FirhCargarBody):
    try:
        resultado = middleware.insertar_registro_firh(body.tabla, body.datos)
        return resultado
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# PÁGINAS HTML — MÓDULOS CLÍNICOS
# ============================================================================

def _serve_template(name: str):
    path = os.path.join(BASE_DIR, "templates", "index.html")
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="SPA Shell index.html no encontrada")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


@app.get("/modulo-triage", response_class=HTMLResponse)
@app.get("/modulo-triage/", response_class=HTMLResponse)
async def modulo_triage_page():
    """Módulo de Triage — Redireccionado a SPA"""
    _log_event("info", "Acceso al Módulo Triage")
    return _serve_template("index.html")


@app.get("/modulo-medico", response_class=HTMLResponse)
@app.get("/modulo-medico/", response_class=HTMLResponse)
async def modulo_medico_page():
    """Módulo Médico — Redireccionado a SPA"""
    _log_event("info", "Acceso al Módulo Médico")
    return _serve_template("index.html")


@app.get("/reportes", response_class=HTMLResponse)
@app.get("/reportes/", response_class=HTMLResponse)
async def reportes_page():
    """Dashboard de Reportes y Estadísticas — Redireccionado a SPA"""
    _log_event("info", "Acceso al Dashboard de Reportes")
    return _serve_template("index.html")


# ============================================================================
# SEGURIDAD: Endpoint de autenticación OAuth2 básico
# ============================================================================

class TokenRequest(BaseModel):
    username: str
    password: str

USERS_DB = {
    "admin": {"password": "admin123", "role": "admin", "nombre": "Administrador"},
    "medico": {"password": "medico123", "role": "medico", "nombre": "Dr. Carlos Rodríguez"},
    "enfermero": {"password": "enfermero123", "role": "enfermero", "nombre": "Enf. Ana Torres"},
}

@app.post("/api/auth/token")
async def obtener_token(req: TokenRequest):
    """
    Endpoint OAuth2 / SMART on FHIR — emite JWT firmado con HS256.
    Incluir en peticiones como:  Authorization: Bearer <token>
    """
    user = USERS_DB.get(req.username)
    if not user or user["password"] != req.password:
        _log_event("warn", f"Intento de autenticación fallido para: {req.username}")
        raise HTTPException(status_code=401, detail="Credenciales inválidas")

    token = _generar_jwt(req.username, user["role"])
    _log_event("ok", f"JWT emitido para: {req.username} ({user['role']})")
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": JWT_EXPIRE_MINUTES * 60,
        "scope": "patient/*.read patient/*.write fhir/read fhir/write",
        "usuario": user["nombre"],
        "rol": user["role"],
        "mensaje": f"JWT válido por {JWT_EXPIRE_MINUTES} minutos."
    }


@app.get("/api/auth/verify")
async def verificar_autenticacion(token=Depends(verificar_token)):
    """Verifica si el token Bearer es válido"""
    if token is None:
        return {"autenticado": False, "modo": "demo", "mensaje": "Sin token (modo demo público)"}
    return {"autenticado": True, "modo": "seguro", "token_valido": True}


# ============================================================================
# ESTADÍSTICAS FHIR EN TIEMPO REAL
# ============================================================================

@app.get("/api/v1/fhir/stats")
async def get_fhir_stats():
    """Estadísticas globales de recursos FHIR — suma de los 3 nodos con distribución de triage"""
    import httpx
    import asyncio
    from backend.fhir_app.services.fhir_service import NODE_URLS
    stats = {
        "patients": 0, 
        "encounters": 0, 
        "conditions": 0, 
        "medications": 0, 
        "observations": 0,
        "triage_distribution": {"I": 0, "II": 0, "III": 0, "IV": 0, "V": 0}
    }
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            # 1. Obtener conteo de recursos
            for nodo_url in NODE_URLS.values():
                for resource, field in [
                    ("Patient", "patients"), ("Encounter", "encounters"),
                    ("Condition", "conditions"), ("MedicationRequest", "medications"),
                    ("Observation", "observations")
                ]:
                    try:
                        r = await client.get(
                            f"{nodo_url}/{resource}?_count=0",
                            headers={"Accept": "application/fhir+json"}
                        )
                        if r.status_code == 200:
                            stats[field] += r.json().get("total", 0)
                    except Exception:
                        pass
            
            # 2. Obtener distribución de Triage desde Encounter
            async def fetch_encounters(url):
                try:
                    r = await client.get(
                        f"{url}/Encounter?_count=100",
                        headers={"Accept": "application/fhir+json"}
                    )
                    if r.status_code == 200:
                        return r.json().get("entry", [])
                except:
                    pass
                return []

            tasks = [fetch_encounters(url) for url in NODE_URLS.values()]
            results = await asyncio.gather(*tasks)

            for entry_list in results:
                for entry in entry_list:
                    res = entry.get("resource", {})
                    for ext in res.get("extension", []):
                        if ext.get("url") == "http://www.minsalud.gov.co/triage":
                            coding = ext.get("valueCodeableConcept", {}).get("coding", [])
                            if coding:
                                code = coding[0].get("code")
                                if code in stats["triage_distribution"]:
                                    stats["triage_distribution"][code] += 1
                                    
        _log_event("info", f"Stats FHIR (3 nodos): {stats['patients']} pacientes, Triage: {stats['triage_distribution']}")
    except Exception as e:
        _log_event("warn", f"Error stats FHIR: {e}")
    return stats


@app.get("/api/v1/fhir/diagnosticos-frecuentes")
async def get_diagnosticos_frecuentes():
    """Retorna los diagnósticos CIE-10 más frecuentes registrados en FHIR"""
    import httpx
    import asyncio
    from backend.fhir_app.services.fhir_service import NODE_URLS
    try:
        async def fetch_conditions(url):
            try:
                async with httpx.AsyncClient(timeout=4.0) as client:
                    r = await client.get(
                        f"{url}/Condition?_count=50",
                        headers={"Accept": "application/fhir+json"}
                    )
                    if r.status_code == 200:
                        return r.json().get("entry", [])
            except:
                pass
            return []

        tasks = [fetch_conditions(url) for url in NODE_URLS.values()]
        results = await asyncio.gather(*tasks)
        
        conteo = {}
        for entry_list in results:
            for entry in entry_list:
                resource = entry.get("resource", {})
                code_obj = resource.get("code", {})
                codings = code_obj.get("coding", [])
                text = code_obj.get("text", "Sin descripción")
                if codings:
                    code = codings[0].get("code", "???")
                    display = codings[0].get("display") or text
                    key = code
                    if key not in conteo:
                        conteo[key] = {"code": code, "description": display, "count": 0}
                    conteo[key]["count"] += 1

        sorted_diags = sorted(conteo.values(), key=lambda x: x["count"], reverse=True)
        return {"diagnosticos": sorted_diags[:10], "total": len(sorted_diags)}
    except Exception as e:
        return {"diagnosticos": [], "error": str(e)}


# ============================================================================
# LOGS DEL SISTEMA Y MONITOREO
# ============================================================================

@app.get("/api/system/logs")
async def get_system_logs(limit: int = 50):
    """Retorna los últimos eventos del sistema (failover, errores, accesos)"""
    logs = list(reversed(_system_logs[-limit:]))
    return {"logs": logs, "total": len(_system_logs)}


@app.get("/api/v1/fhir/failover-test")
async def test_fhir_failover(nodo: str = "nodo1"):
    """
    Prueba de failover a nivel FHIR: demuestra que si un nodo HAPI FHIR no responde,
    el sistema automáticamente redirige al siguiente nodo disponible.
    """
    from backend.fhir_app.services.fhir_service import NODE_URLS, NODO_CIUDAD
    import httpx, time as _t
    _log_event("warn", f"[FHIR FAILOVER] Iniciando prueba para {nodo}")
    inicio = _t.time()
    resultados = []
    nodo_exitoso = None

    for nodo_id, base_url in NODE_URLS.items():
        t0 = _t.time()
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{base_url}/metadata", headers={"Accept": "application/fhir+json"})
                if r.status_code == 200:
                    lat = round((_t.time() - t0) * 1000, 2)
                    resultados.append({"nodo": NODO_CIUDAD[nodo_id], "status": "ok", "latencia_ms": lat})
                    if nodo_exitoso is None:
                        nodo_exitoso = NODO_CIUDAD[nodo_id]
                else:
                    resultados.append({"nodo": NODO_CIUDAD[nodo_id], "status": "error", "code": r.status_code})
        except Exception as e:
            resultados.append({"nodo": NODO_CIUDAD[nodo_id], "status": "caido", "error": str(e)[:100]})

    elapsed = round((_t.time() - inicio) * 1000, 2)
    _log_event("ok", f"[FHIR FAILOVER] Completado en {elapsed}ms — nodo activo: {nodo_exitoso}")
    return {
        "success": nodo_exitoso is not None,
        "nodo_primario_solicitado": nodo,
        "nodo_fhir_activo": nodo_exitoso,
        "tiempo_total_ms": elapsed,
        "dentro_limite_5s": elapsed < 5000,
        "nodos": resultados,
    }


@app.get("/api/system/failover-test")
async def test_failover(nodo: str = "nodo1"):
    """
    Simula y documenta el comportamiento de failover cuando un nodo cae.
    Demuestra la redirección automática al nodo secundario.
    """
    _log_event("warn", f"[SIMULACIÓN] Iniciando prueba de failover para {nodo}")
    import time
    inicio = time.time()

    # Obtener el nodo primario a simular como caído
    nodos = middleware.NODOS_CONFIG
    nodo_target = next((n for n in nodos if n["id"] == nodo), nodos[0])

    # Intentar escritura con failover
    try:
        conn, nodo_usado = middleware._conectar_con_failover(nodo_target)
        elapsed = time.time() - inicio
        failover = nodo_usado["id"] != nodo_target["id"]

        if conn:
            conn.close()
            msg = f"Failover {'activado' if failover else 'no necesario'}: {nodo_target['ciudad']} → {nodo_usado['ciudad']}"
            _log_event("ok" if not failover else "warn", msg)
            return {
                "success": True,
                "failover_activado": failover,
                "nodo_solicitado": nodo_target["ciudad"],
                "nodo_usado": nodo_usado["ciudad"],
                "tiempo_failover_ms": round(elapsed * 1000, 2),
                "dentro_limite_5s": elapsed < 5.0,
                "mensaje": msg
            }
        else:
            _log_event("err", f"TODOS LOS NODOS CAÍDOS durante prueba de failover")
            return {"success": False, "mensaje": "Todos los nodos están caídos"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================================================
# MÉTRICAS PROMETHEUS
# ============================================================================

@app.get("/metrics", response_class=PlainTextResponse)
async def prometheus_metrics():
    """Endpoint de métricas en formato Prometheus para Grafana"""
    import httpx
    lines = [
        "# HELP hc_app_up Sistema Historia Clínica operativo",
        "# TYPE hc_app_up gauge",
        "hc_app_up 1",
        "",
    ]

    # Estado de nodos
    try:
        nodos = middleware.get_estado_nodos()
        lines += [
            "# HELP hc_nodo_up Estado del nodo PostgreSQL (1=up, 0=down)",
            "# TYPE hc_nodo_up gauge",
        ]
        for n in nodos:
            ciudad = n.get("ciudad", n["id"])
            val = 1 if n.get("activo", False) else 0
            lines.append(f'hc_nodo_up{{nodo="{n["id"]}",ciudad="{ciudad}"}} {val}')
        lines.append("")

        # Latencia por nodo
        lines += [
            "# HELP hc_nodo_latency_ms Latencia de conexion PostgreSQL por nodo (ms)",
            "# TYPE hc_nodo_latency_ms gauge",
        ]
        for n in nodos:
            ciudad = n.get("ciudad", n["id"])
            lat = n.get("latencia_ms")
            if lat is not None:
                lines.append(f'hc_nodo_latency_ms{{nodo="{n["id"]}",ciudad="{ciudad}"}} {lat}')
        lines.append("")

        # Registros pendientes de sincronizacion
        lines += [
            "# HELP hc_nodo_sync_pending Registros pendientes de sincronizacion por nodo",
            "# TYPE hc_nodo_sync_pending gauge",
        ]
        for n in nodos:
            ciudad = n.get("ciudad", n["id"])
            pendientes = n.get("pendientes_sincronizacion", 0)
            lines.append(f'hc_nodo_sync_pending{{nodo="{n["id"]}",ciudad="{ciudad}"}} {pendientes}')
        lines.append("")
    except Exception as e:
        lines.append(f"# ERROR obteniendo nodos: {e}")

    # Stats FHIR básicas (sincrónico simplificado)
    try:
        import httpx as hx
        lines += [
            "# HELP hc_fhir_resources_total Total de recursos FHIR por tipo",
            "# TYPE hc_fhir_resources_total gauge",
        ]
        async with hx.AsyncClient(timeout=5.0) as client:
            urls = [
                os.getenv("FHIR_NODO1_URL", "http://hapi-fhir-sincelejo:8080/fhir"),
                os.getenv("FHIR_NODO2_URL", "http://hapi-fhir-bogota:8080/fhir"),
                os.getenv("FHIR_NODO3_URL", "http://hapi-fhir-medellin:8080/fhir")
            ]
            for resource in ["Patient", "Encounter", "Condition", "MedicationRequest"]:
                total = 0
                for url in urls:
                    try:
                        r = await client.get(
                            f"{url}/{resource}?_count=0",
                            headers={"Accept": "application/fhir+json"}
                        )
                        if r.status_code == 200:
                            total += r.json().get("total", 0)
                    except Exception:
                        pass
                lines.append(f'hc_fhir_resources_total{{resource="{resource}"}} {total}')
    except Exception as e:
        lines.append(f"# ERROR stats FHIR: {e}")

    lines += [
        "",
        "# HELP hc_system_log_events_total Total de eventos en el log del sistema",
        "# TYPE hc_system_log_events_total counter",
        f"hc_system_log_events_total {len(_system_logs)}",
    ]

    return "\n".join(lines) + "\n"


@app.get("/metrics/nodo/{ciudad}", response_class=PlainTextResponse)
async def prometheus_metrics_nodo(ciudad: str):
    """Métricas específicas por ciudad/nodo"""
    ciudad_map = {"sincelejo": "nodo1", "bogota": "nodo2", "medellin": "nodo3"}
    nodo_id = ciudad_map.get(ciudad.lower(), ciudad)
    nodos = middleware.get_estado_nodos()
    nodo = next((n for n in nodos if n["id"] == nodo_id), None)
    if not nodo:
        return f"# nodo {ciudad} no encontrado\n"

    val = 1 if nodo.get("activo", False) else 0
    return (
        f'# HELP hc_nodo_up Estado nodo {ciudad}\n'
        f'# TYPE hc_nodo_up gauge\n'
        f'hc_nodo_up{{ciudad="{nodo.get("ciudad",ciudad)}"}} {val}\n'
    )


# ============================================================================
# ESTÁTICOS (al final para no tapar rutas)
# ============================================================================
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

PORT = 8001

if __name__ == "__main__":
    import uvicorn
    _log_event("info", "Aplicación iniciada")
    print("\n  → Dashboard:      http://localhost:{}/".format(PORT))
    print("  → Triage:         http://localhost:{}/modulo-triage".format(PORT))
    print("  → Módulo Médico:  http://localhost:{}/modulo-medico".format(PORT))
    print("  → Reportes:       http://localhost:{}/reportes".format(PORT))
    print("  → FHIR Docs:      http://localhost:{}/docs".format(PORT))
    print("  → Prometheus:     http://localhost:9090")
    print("  → Grafana:        http://localhost:3000  (admin/admin123)\n")
    uvicorn.run(app, host="0.0.0.0", port=PORT)

