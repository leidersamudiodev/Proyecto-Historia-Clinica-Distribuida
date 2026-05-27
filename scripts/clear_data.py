#!/usr/bin/env python3
# clear_data.py — Purga limpia de todos los registros de prueba en PostgreSQL y HAPI FHIR.

import os
import sys
import psycopg2
import httpx
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Configuración de base de datos
USE_DOCKER_NAMES = os.getenv("USE_DOCKER_NAMES", "false").lower() == "true"

NODOS_DB = [
    {
        "id": "nodo1",
        "ciudad": "Sincelejo",
        "host": "pg_nodo1" if USE_DOCKER_NAMES else "localhost",
        "port": 5432 if USE_DOCKER_NAMES else 5433,
        "user": "admin",
        "password": "admin",
        "dbname": "historia_clinica",
    },
    {
        "id": "nodo2",
        "ciudad": "Bogotá",
        "host": "pg_nodo2" if USE_DOCKER_NAMES else "localhost",
        "port": 5432 if USE_DOCKER_NAMES else 5434,
        "user": "admin",
        "password": "admin",
        "dbname": "historia_clinica",
    },
    {
        "id": "nodo3",
        "ciudad": "Medellín",
        "host": "pg_nodo3" if USE_DOCKER_NAMES else "localhost",
        "port": 5432 if USE_DOCKER_NAMES else 5435,
        "user": "admin",
        "password": "admin",
        "dbname": "historia_clinica",
    },
]

# Servidores HAPI FHIR
# Si se corre fuera de la red de Docker, usa localhost y los puertos expuestos.
# Si se corre dentro, usa los nombres de los contenedores.
FHIR_URLS = [
    os.getenv("FHIR_NODO1_URL", "http://hapi-fhir-sincelejo:8080/fhir") if USE_DOCKER_NAMES else "http://localhost:8081/fhir",
    os.getenv("FHIR_NODO2_URL", "http://hapi-fhir-bogota:8080/fhir") if USE_DOCKER_NAMES else "http://localhost:8082/fhir",
    os.getenv("FHIR_NODO3_URL", "http://hapi-fhir-medellin:8080/fhir") if USE_DOCKER_NAMES else "http://localhost:8083/fhir",
]

def purge_postgres():
    logger.info("🗑️ Iniciando purga en PostgreSQL...")
    for db in NODOS_DB:
        logger.info(f"🔌 Conectando a PostgreSQL {db['ciudad']} ({db['host']}:{db['port']})...")
        try:
            conn = psycopg2.connect(
                host=db["host"],
                port=db["port"],
                user=db["user"],
                password=db["password"],
                dbname=db["dbname"],
                connect_timeout=5
            )
            conn.autocommit = True
            with conn.cursor() as cur:
                logger.info(f"🧹 Limpiando tablas en {db['ciudad']}...")
                # Truncar las tablas en orden inverso de llaves foráneas
                cur.execute("TRUNCATE TABLE egreso, diagnostico, tecnologia_salud, atencion, usuario RESTART IDENTITY CASCADE;")
                logger.info(f"✅ Tablas purgadas con éxito en {db['ciudad']}")
            conn.close()
        except Exception as e:
            logger.error(f"❌ Error al purgar PostgreSQL en {db['ciudad']}: {e}")

def purge_fhir():
    logger.info("🗑️ Iniciando purga en HAPI FHIR...")
    headers = {
        "Accept": "application/fhir+json",
        "Content-Type": "application/fhir+json"
    }
    
    resource_types = ["MedicationRequest", "Condition", "Observation", "Encounter", "Patient"]
    
    for fhir_url in FHIR_URLS:
        logger.info(f"🔌 Conectando a servidor HAPI FHIR: {fhir_url}...")
        try:
            # 1. Verificar conectividad
            with httpx.Client(timeout=10.0) as client:
                r_meta = client.get(f"{fhir_url}/metadata", headers=headers)
                if r_meta.status_code != 200:
                    logger.warning(f"⚠️ Servidor FHIR {fhir_url} no respondió correctamente a metadata. Intentando continuar...")
                
                # 2. Eliminar recursos uno por uno
                for res_type in resource_types:
                    logger.info(f"🔍 Buscando recursos {res_type} en {fhir_url}...")
                    
                    # Buscar recursos
                    r_search = client.get(f"{fhir_url}/{res_type}?_count=1000", headers=headers)
                    if r_search.status_code == 200:
                        bundle = r_search.json()
                        entries = bundle.get("entry", [])
                        logger.info(f"📋 Encontrados {len(entries)} recursos de tipo {res_type}")
                        
                        deleted_count = 0
                        for entry in entries:
                            res = entry.get("resource", {})
                            res_id = res.get("id")
                            if res_id:
                                # Borrar el recurso
                                del_url = f"{fhir_url}/{res_type}/{res_id}"
                                r_del = client.delete(del_url, headers=headers)
                                if r_del.status_code in (200, 204):
                                    deleted_count += 1
                                else:
                                    # HAPI FHIR a veces requiere expurgar
                                    client.delete(f"{del_url}?_expunge=true", headers=headers)
                                    deleted_count += 1
                        
                        if deleted_count > 0:
                            logger.info(f"✅ Eliminados {deleted_count} recursos de tipo {res_type}")
                    else:
                        logger.warning(f"⚠️ Error al buscar {res_type} en {fhir_url}: {r_search.status_code}")
                        
        except Exception as e:
            logger.error(f"❌ Error al purgar servidor HAPI FHIR {fhir_url}: {e}")

if __name__ == "__main__":
    logger.info("🚀 =====================================================")
    logger.info("🚀 PURGA TOTAL DE HISTORIAS CLÍNICAS DE PRUEBA")
    logger.info("🚀 =====================================================")
    
    purge_postgres()
    purge_fhir()
    
    logger.info("✨ =====================================================")
    logger.info("✨ PROCESO DE PURGA COMPLETADO")
    logger.info("✨ =====================================================")
