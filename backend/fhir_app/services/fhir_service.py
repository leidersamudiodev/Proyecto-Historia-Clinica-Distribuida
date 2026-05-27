# backend/fhir_app/services/fhir_service.py
"""
FHIRService — Enruta peticiones a 3 instancias HAPI FHIR independientes.
El sharding sigue el mismo criterio del middleware.py:
  - Nodo 1 (Sincelejo):  documento_id < 4.000.000.000
  - Nodo 2 (Bogotá):    4.000.000.000 <= documento_id < 7.000.000.000
  - Nodo 3 (Medellín):  documento_id >= 7.000.000.000
"""

import httpx
import os
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# URLs de las 3 instancias FHIR (sobrescribibles por variables de entorno)
FHIR_NODO1_URL = os.getenv("FHIR_NODO1_URL", "http://hapi-fhir-sincelejo:8080/fhir")
FHIR_NODO2_URL = os.getenv("FHIR_NODO2_URL", "http://hapi-fhir-bogota:8080/fhir")
FHIR_NODO3_URL = os.getenv("FHIR_NODO3_URL", "http://hapi-fhir-medellin:8080/fhir")

# Fallback cuando se corre en local sin Docker (localhost)
FHIR_LOCAL_URL = os.getenv("FHIR_LOCAL_URL", "http://localhost:8081/fhir")

NODE_URLS = {
    "nodo1": FHIR_NODO1_URL,
    "nodo2": FHIR_NODO2_URL,
    "nodo3": FHIR_NODO3_URL,
}

NODO_CIUDAD = {
    "nodo1": "Sincelejo",
    "nodo2": "Bogotá",
    "nodo3": "Medellín",
}


def _get_nodo_por_documento(numero_documento: str) -> str:
    """Determina el nodo FHIR según el número de documento (mismo criterio que middleware.py)."""
    try:
        val = int(numero_documento)
        if val < 4_000_000_000:
            return "nodo1"
        elif val < 7_000_000_000:
            return "nodo2"
        else:
            return "nodo3"
    except (ValueError, TypeError):
        return "nodo1"  # default Sincelejo


def _get_url_por_documento(numero_documento: str) -> str:
    nodo = _get_nodo_por_documento(numero_documento)
    return NODE_URLS[nodo]


class FHIRService:
    """Servicio para comunicación distribuida con las 3 instancias HAPI FHIR."""

    def __init__(self):
        self.headers = {
            "Content-Type": "application/fhir+json",
            "Accept": "application/fhir+json",
            "Cache-Control": "no-cache, no-store, must-revalidate",
        }
        self.timeout = 30.0
        self.NODE_URLS = NODE_URLS
        self.NODO_CIUDAD = NODO_CIUDAD

    def _get_base_url(self, documento_id: str = None, nodo: str = None) -> str:
        """Retorna la URL base del servidor FHIR correcto."""
        if nodo and nodo in NODE_URLS:
            return NODE_URLS[nodo]
        if documento_id:
            return _get_url_por_documento(documento_id)
        return FHIR_NODO1_URL  # default

    async def _post_fhir(self, url: str, resource_json: str, fallback_urls: list = None) -> Dict[str, Any]:
        """
        POST a un servidor FHIR con fallback automático a otros nodos si el primero falla.
        """
        urls_to_try = [url] + (fallback_urls or [])
        last_error = None

        for try_url in urls_to_try:
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(try_url, content=resource_json, headers=self.headers)
                    response.raise_for_status()
                    data = response.json()
                    
                    # Inject _nodo for frontend tracing
                    if "8080" in try_url: data["_nodo"] = "Sincelejo (Primario)" if try_url == url else "Sincelejo (Respaldo)"
                    if "8081" in try_url: data["_nodo"] = "Bogotá (Primario)" if try_url == url else "Bogotá (Respaldo)"
                    if "8082" in try_url: data["_nodo"] = "Medellín (Primario)" if try_url == url else "Medellín (Respaldo)"
                    
                    if try_url != url:
                        logger.warning(f"[FHIR FAILOVER] Usado {try_url} en lugar del nodo primario")
                    return data
            except httpx.HTTPStatusError as e:
                last_error = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
                logger.warning(f"[FHIR] Error en {try_url}: {last_error}")
            except Exception as e:
                last_error = str(e)
                logger.warning(f"[FHIR] Conexión fallida a {try_url}: {last_error}")

        raise Exception(f"Todos los nodos FHIR fallaron. Último error: {last_error}")

    async def _get_fhir(self, url: str, params: dict = None) -> Optional[Dict[str, Any]]:
        """GET a un servidor FHIR."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params, headers=self.headers)
                if response.status_code == 404:
                    return None
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise Exception(f"HTTP {e.response.status_code}: {e.response.text}")
        except Exception as e:
            raise Exception(f"Error GET FHIR: {str(e)}")

    # ─────────────────────────────────────────────────────────
    # PATIENT
    # ─────────────────────────────────────────────────────────
    async def get_next_global_patient_id(self) -> int:
        """Encuentra el ID más alto usado en cualquier nodo y devuelve el siguiente (min 1000)."""
        max_id = 999
        async with httpx.AsyncClient(timeout=10.0) as client:
            for n_id, n_url in NODE_URLS.items():
                try:
                    r = await client.get(f"{n_url}/Patient?_count=1000", headers=self.headers)
                    if r.status_code == 200:
                        data = r.json()
                        for entry in data.get("entry", []):
                            pid_str = entry.get("resource", {}).get("id", "")
                            if pid_str.startswith("P-"):
                                pid_str = pid_str[2:]
                            if pid_str.isdigit():
                                pid = int(pid_str)
                                if pid > max_id:
                                    max_id = pid
                except Exception as e:
                    logger.warning(f"Error al buscar max_id en {n_id}: {e}")
        return max_id + 1

    async def create_patient(self, patient, documento_id: str = None) -> Dict[str, Any]:
        """Crea un paciente en la instancia FHIR correcta asignándole un ID global único."""
        patient_json = patient.json() if hasattr(patient, "json") else str(patient)

        # Extraer número de documento
        if not documento_id:
            try:
                import json as _json
                d = _json.loads(patient_json)
                identifiers = d.get("identifier", [])
                if identifiers:
                    documento_id = identifiers[0].get("value", "")
            except Exception:
                pass

        nodo = _get_nodo_por_documento(documento_id or "")
        primary_url = NODE_URLS[nodo]
        
        # 1. Obtener ID numérico global unificado y agregar prefijo 'P-' para cumplir con HAPI FHIR
        next_id_num = await self.get_next_global_patient_id()
        next_id = f"P-{next_id_num}"
        
        # 2. Inyectar el ID en el recurso FHIR
        import json as _json
        patient_dict = _json.loads(patient_json)
        patient_dict["id"] = next_id
        patient_json = _json.dumps(patient_dict)
        
        urls_to_try = [primary_url] + [v for k, v in NODE_URLS.items() if k != nodo]
        last_error = None
        
        # 3. Forzar la creación usando PUT iterando por los nodos disponibles (Failover)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for try_base_url in urls_to_try:
                put_url = f"{try_base_url}/Patient/{next_id}"
                try:
                    response = await client.put(put_url, content=patient_json, headers=self.headers)
                    response.raise_for_status()
                    data = response.json()
                    
                    # Identificar qué nodo respondió exitosamente
                    for n_id, n_url in NODE_URLS.items():
                        if n_url == try_base_url:
                            if try_base_url == primary_url:
                                data["_nodo"] = NODO_CIUDAD[n_id]
                            else:
                                data["_nodo"] = f"{NODO_CIUDAD[n_id]} (Respaldo)"
                            break
                    
                    if try_base_url != primary_url:
                        logger.warning(f"[FHIR FAILOVER] Creado paciente {next_id} en {try_base_url} porque el primario falló.")
                        
                    return data
                except Exception as e:
                    last_error = str(e)
                    logger.warning(f"[FHIR] Fallo PUT en {put_url}: {last_error}")

        raise Exception(f"Todos los nodos FHIR fallaron. Último error: {last_error}")

    async def get_patient(self, patient_id: str) -> Optional[Dict[str, Any]]:
        """Busca el paciente en los 3 nodos (puede estar en cualquiera)."""
        for nodo_id, base_url in NODE_URLS.items():
            try:
                result = await self._get_fhir(f"{base_url}/Patient/{patient_id}")
                if result:
                    logger.info(f"[FHIR] Patient {patient_id} encontrado en {NODO_CIUDAD[nodo_id]}")
                    return result
            except Exception as e:
                logger.warning(f"[FHIR] Error al buscar paciente en {nodo_id}: {e}")
                pass
        return None

    async def search_patient_by_identifier(self, identifier: str) -> Dict[str, Any]:
        """Busca un paciente por número de documento en todos los nodos."""
        nodo = _get_nodo_por_documento(identifier)
        base_url = NODE_URLS[nodo]

        # Primero busca en el nodo que corresponde por sharding
        try:
            result = await self._get_fhir(f"{base_url}/Patient", params={"identifier": identifier})
            if result and result.get("entry"):
                return result
        except Exception:
            pass

        # Fallback: buscar en todos los nodos
        all_entries = []
        for n_id, n_url in NODE_URLS.items():
            try:
                r = await self._get_fhir(f"{n_url}/Patient", params={"identifier": identifier})
                if r and r.get("entry"):
                    all_entries.extend(r["entry"])
            except Exception:
                pass

        return {"resourceType": "Bundle", "type": "searchset", "total": len(all_entries), "entry": all_entries}

    async def list_all_patients(self, page: int = 1, size: int = 10) -> Dict[str, Any]:
        """Lista pacientes de todos los nodos (simplificado, prioriza nodo1 y suma los demás)"""
        all_entries = []
        for n_id, n_url in NODE_URLS.items():
            try:
                r = await self._get_fhir(f"{n_url}/Patient", params={"_count": size})
                if r and r.get("entry"):
                    all_entries.extend(r["entry"])
            except Exception:
                pass
        return {"resourceType": "Bundle", "total": len(all_entries), "entry": all_entries}

    async def search_patients_general(self, q: str) -> Dict[str, Any]:
        """Busca pacientes por nombre o identificador en todos los nodos"""
        all_entries = []
        for n_id, n_url in NODE_URLS.items():
            try:
                r_name = await self._get_fhir(f"{n_url}/Patient", params={"name": q})
                if r_name and r_name.get("entry"): all_entries.extend(r_name["entry"])
                
                r_id = await self._get_fhir(f"{n_url}/Patient", params={"identifier": q})
                if r_id and r_id.get("entry"): all_entries.extend(r_id["entry"])
            except Exception:
                pass
                
        # Remover duplicados
        unique = {e["resource"]["id"]: e for e in all_entries if "resource" in e}
        return {"resourceType": "Bundle", "total": len(unique), "entry": list(unique.values())}

    async def update_patient(self, patient_id: str, patient) -> Dict[str, Any]:
        """Actualiza un paciente buscándolo en todos los nodos."""
        patient_json = patient.json() if hasattr(patient, "json") else str(patient)
        for nodo_id, base_url in NODE_URLS.items():
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.put(
                        f"{base_url}/Patient/{patient_id}",
                        content=patient_json,
                        headers=self.headers
                    )
                    if response.status_code in (200, 201):
                        return response.json()
            except Exception:
                continue
        raise Exception(f"No se pudo actualizar el paciente {patient_id} en ningún nodo FHIR")

    async def delete_patient(self, patient_id: str) -> bool:
        """Elimina un paciente de todos los nodos donde exista."""
        deleted = False
        for nodo_id, base_url in NODE_URLS.items():
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.delete(
                        f"{base_url}/Patient/{patient_id}",
                        headers=self.headers
                    )
                    if response.status_code in (200, 204):
                        deleted = True
            except Exception:
                pass
        return deleted

    # ─────────────────────────────────────────────────────────
    # ENCOUNTER / TRIAGE
    # ─────────────────────────────────────────────────────────

    async def create_encounter(self, encounter, nodo: str = "nodo1") -> Dict[str, Any]:
        """Crea un Encounter en el nodo FHIR especificado."""
        enc_json = encounter.json() if hasattr(encounter, "json") else str(encounter)
        base_url = NODE_URLS.get(nodo, FHIR_NODO1_URL)
        fallback_urls = [v + "/Encounter" for k, v in NODE_URLS.items() if k != nodo]
        return await self._post_fhir(f"{base_url}/Encounter", enc_json, fallback_urls)

    async def create_observation(self, observation, nodo: str = "nodo1") -> Dict[str, Any]:
        """Crea una Observation (signos vitales) en el nodo FHIR especificado."""
        obs_json = observation.json() if hasattr(observation, "json") else str(observation)
        base_url = NODE_URLS.get(nodo, FHIR_NODO1_URL)
        fallback_urls = [v + "/Observation" for k, v in NODE_URLS.items() if k != nodo]
        return await self._post_fhir(f"{base_url}/Observation", obs_json, fallback_urls)

    async def create_condition(self, condition, nodo: str = "nodo1") -> Dict[str, Any]:
        """Crea una Condition (diagnóstico) en el nodo FHIR especificado."""
        cond_json = condition.json() if hasattr(condition, "json") else str(condition)
        base_url = NODE_URLS.get(nodo, FHIR_NODO1_URL)
        fallback_urls = [v + "/Condition" for k, v in NODE_URLS.items() if k != nodo]
        return await self._post_fhir(f"{base_url}/Condition", cond_json, fallback_urls)

    async def create_medication_request(self, med_request, nodo: str = "nodo1") -> Dict[str, Any]:
        """Crea un MedicationRequest en el nodo FHIR especificado."""
        med_json = med_request.json() if hasattr(med_request, "json") else str(med_request)
        base_url = NODE_URLS.get(nodo, FHIR_NODO1_URL)
        fallback_urls = [v + "/MedicationRequest" for k, v in NODE_URLS.items() if k != nodo]
        return await self._post_fhir(f"{base_url}/MedicationRequest", med_json, fallback_urls)

    # ─────────────────────────────────────────────────────────
    # HISTORIA CLÍNICA COMPLETA
    # ─────────────────────────────────────────────────────────

    async def get_patient_clinical_record(self, patient_id: str, document_id: str = None) -> Dict[str, Any]:
        """
        Obtiene la historia clínica completa del paciente buscando en TODOS los nodos.
        Esto es esencial para escenarios de failover donde los recursos clínicos
        pueden haberse guardado en un nodo de respaldo diferente al primario.
        """
        patient = None
        encounters_list = []
        observations_list = []
        conditions_list = []
        meds_list = []
        nodos_consultados = []
        internal_patient_id = patient_id

        async with httpx.AsyncClient(timeout=30.0) as client:
            # 1. Buscar al paciente en todos los nodos disponibles
            if document_id:
                search_result = await self.search_patient_by_identifier(document_id)
                if search_result and search_result.get("entry"):
                    patient = search_result["entry"][0]["resource"]
                    internal_patient_id = patient["id"]

            if not patient:
                for n_id, b_url in NODE_URLS.items():
                    try:
                        r = await client.get(f"{b_url}/Patient/{patient_id}", headers=self.headers)
                        if r.status_code == 200:
                            patient = r.json()
                            internal_patient_id = patient["id"]
                            break
                    except Exception:
                        continue

            if not patient:
                return {"success": False, "detail": "Paciente no encontrado en ningún nodo FHIR"}

            # 2. Obtener recursos clínicos de TODOS los nodos disponibles (failover-aware)
            seen_ids = {"enc": set(), "obs": set(), "cond": set(), "med": set()}

            for n_id, base_url in NODE_URLS.items():
                try:
                    # Encounters
                    r = await client.get(
                        f"{base_url}/Encounter",
                        params={"subject": f"Patient/{internal_patient_id}", "_sort": "-date"},
                        headers=self.headers
                    )
                    if r.status_code == 200 and r.json().get("entry"):
                        for item in r.json().get("entry", []):
                            res = item["resource"]
                            if res["id"] not in seen_ids["enc"]:
                                seen_ids["enc"].add(res["id"])
                                encounters_list.append(res)

                    # Observations
                    r = await client.get(
                        f"{base_url}/Observation",
                        params={"subject": f"Patient/{internal_patient_id}", "_sort": "-date"},
                        headers=self.headers
                    )
                    if r.status_code == 200 and r.json().get("entry"):
                        for item in r.json().get("entry", []):
                            res = item["resource"]
                            if res["id"] not in seen_ids["obs"]:
                                seen_ids["obs"].add(res["id"])
                                observations_list.append(res)

                    # Conditions
                    r = await client.get(
                        f"{base_url}/Condition",
                        params={"subject": f"Patient/{internal_patient_id}"},
                        headers=self.headers
                    )
                    if r.status_code == 200 and r.json().get("entry"):
                        for item in r.json().get("entry", []):
                            res = item["resource"]
                            if res["id"] not in seen_ids["cond"]:
                                seen_ids["cond"].add(res["id"])
                                conditions_list.append(res)

                    # MedicationRequests
                    r = await client.get(
                        f"{base_url}/MedicationRequest",
                        params={"subject": f"Patient/{internal_patient_id}"},
                        headers=self.headers
                    )
                    if r.status_code == 200 and r.json().get("entry"):
                        for item in r.json().get("entry", []):
                            res = item["resource"]
                            if res["id"] not in seen_ids["med"]:
                                seen_ids["med"].add(res["id"])
                                meds_list.append(res)

                    nodos_consultados.append(NODO_CIUDAD[n_id])
                except Exception as e:
                    logger.warning(f"[HC] Nodo {NODO_CIUDAD[n_id]} no disponible: {e}")

        return {
            "success": True,
            "patient": patient,
            "encounters": encounters_list,
            "observations": observations_list,
            "conditions": conditions_list,
            "medicationRequests": meds_list,
            "nodos_consultados": nodos_consultados,
        }

    # ─────────────────────────────────────────────────────────
    # SALUD DEL SERVIDOR
    # ─────────────────────────────────────────────────────────

    async def check_server_health(self) -> Dict[str, Any]:
        """Verifica el estado de las 3 instancias HAPI FHIR."""
        results = {}
        for nodo_id, base_url in NODE_URLS.items():
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    r = await client.get(f"{base_url}/metadata", headers={"Accept": "application/fhir+json"})
                    r.raise_for_status()
                    data = r.json()
                    results[nodo_id] = {
                        "status": "ok",
                        "ciudad": NODO_CIUDAD[nodo_id],
                        "url": base_url,
                        "fhirVersion": data.get("fhirVersion", "R4"),
                    }
            except Exception as e:
                results[nodo_id] = {
                    "status": "error",
                    "ciudad": NODO_CIUDAD[nodo_id],
                    "url": base_url,
                    "error": str(e),
                }
        total_ok = sum(1 for v in results.values() if v["status"] == "ok")
        return {
            "nodos": results,
            "total_operativos": total_ok,
            "total_nodos": len(NODE_URLS),
        }

    async def get_stats_by_nodo(self) -> Dict[str, Any]:
        """Retorna estadísticas de recursos FHIR por cada nodo."""
        stats = {}
        resources = ["Patient", "Encounter", "Condition", "MedicationRequest", "Observation"]

        for nodo_id, base_url in NODE_URLS.items():
            nodo_stats = {"ciudad": NODO_CIUDAD[nodo_id], "activo": False}
            try:
                async with httpx.AsyncClient(timeout=8.0) as client:
                    for resource in resources:
                        try:
                            r = await client.get(
                                f"{base_url}/{resource}?_count=0",
                                headers={"Accept": "application/fhir+json"}
                            )
                            nodo_stats[resource.lower()] = r.json().get("total", 0) if r.status_code == 200 else 0
                        except Exception:
                            nodo_stats[resource.lower()] = 0
                    nodo_stats["activo"] = True
            except Exception as e:
                nodo_stats["error"] = str(e)
            stats[nodo_id] = nodo_stats

        return stats

    async def clear_all_data(self) -> Dict[str, Any]:
        """Borra permanentemente todos los recursos de FHIR usando la operación $expunge."""
        results = {}
        payload = {
            "resourceType": "Parameters", 
            "parameter": [{"name": "expungeEverything", "valueBoolean": True}]
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            for n_id, base_url in NODE_URLS.items():
                try:
                    r = await client.post(
                        f"{base_url}/$expunge",
                        json=payload,
                        headers={"Accept": "application/fhir+json", "Content-Type": "application/fhir+json"}
                    )
                    if r.status_code == 200:
                        results[n_id] = "Expunge Exitoso"
                    else:
                        results[n_id] = f"Error: {r.status_code} - {r.text}"
                except Exception as e:
                    results[n_id] = f"Fallo de conexión: {str(e)}"
                        
        return {"success": True, "details": results}
