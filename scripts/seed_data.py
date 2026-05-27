#!/usr/bin/env python3
import requests
import json
import time

BASE_URL = "http://localhost:8001"

def seed():
    print("🌱 Iniciando proceso de sembrado de datos clínicos reales...")
    
    # 1. Obtener Token JWT
    print("🔑 Autenticándose con la API principal...")
    login_res = requests.post(f"{BASE_URL}/api/auth/token", json={
        "username": "admin",
        "password": "admin123"
    })
    if login_res.status_code != 200:
        print(f"❌ Error al autenticarse: {login_res.text}")
        return
    
    token = login_res.json()["access_token"]
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    print("✅ Autenticado correctamente.")

    # 6 Escenarios clínicos correspondientes a Sincelejo (Nodo 1), Bogotá (Nodo 2), Medellín (Nodo 3)
    patients = [
        # --- NODO 1: SINCELEJO (documento < 4_000_000_000) ---
        {
            "demographics": {
                "tipoDocumento": "CC",
                "numeroDocumento": "1234567891",
                "paisNacionalidad": "CO",
                "nombreCompleto": "Carlos Mario Gómez Torres",
                "fechaNacimiento": "1975-04-12",
                "edad": 51,
                "unidadEdad": "1",
                "sexo": "male",
                "genero": "Masculino",
                "ocupacion": "Conductor de Transporte",
                "voluntadAnticipada": "false",
                "categoriaDiscapacidad": "",
                "paisResidencia": "CO",
                "municipioResidencia": "70001",
                "etnia": "Ninguna"
            },
            "triage": {
                "causaAtencion": "Paciente refiere dolor torácico opresivo de intensidad 8/10 irradiado a miembro superior izquierdo, asociado a diaforesis y disnea de esfuerzo.",
                "frecuenciaCardiaca": 110,
                "frecuenciaRespiratoria": 24,
                "presionSistolica": 150,
                "presionDiastolica": 95,
                "temperatura": 36.8,
                "saturacionOxigeno": 93.0,
                "clasificacionTriage": "I",
                "entornoAtencion": "01",
                "modalidadEntrega": "01",
                "viaIngreso": "01"
            },
            "consultation": {
                "diagnosticoEgreso": {
                    "codigo": "I21.9",
                    "descripcion": "Infarto agudo de miocardio, sin otra especificación",
                    "tipo": "Principal"
                },
                "diagnosticoRel1": {
                    "codigo": "I10",
                    "descripcion": "Hipertensión esencial (primaria)",
                    "tipo": "Relacionado"
                },
                "diagnosticoRel2": {
                    "codigo": "E11.9",
                    "descripcion": "Diabetes mellitus no insulinodependiente sin complicaciones",
                    "tipo": "Relacionado"
                },
                "medicamentos": [
                    {
                        "descripcion": "Aspirina 100mg (Ácido Acetilsalicílico)",
                        "dosis": "100 mg",
                        "viaAdministracion": "01",
                        "frecuencia": "Dosis única diaria",
                        "diasTratamiento": 30,
                        "unidadesAplicadas": 30
                    }
                ],
                "condicionSalida": "01",
                "zonaResidencia": "01",
                "direccionResidencia": "Calle 25 # 14 - 45, Sincelejo"
            }
        },
        {
            "demographics": {
                "tipoDocumento": "CC",
                "numeroDocumento": "2102938475",
                "paisNacionalidad": "CO",
                "nombreCompleto": "María José Rodríguez Díaz",
                "fechaNacimiento": "1988-09-18",
                "edad": 37,
                "unidadEdad": "1",
                "sexo": "female",
                "genero": "Femenino",
                "ocupacion": "Auxiliar Administrativo",
                "voluntadAnticipada": "false",
                "categoriaDiscapacidad": "",
                "paisResidencia": "CO",
                "municipioResidencia": "70001",
                "etnia": "Mestizo"
            },
            "triage": {
                "causaAtencion": "Crisis hipertensiva. Paciente acude por presentar cifras tensionales de 170/100 mmHg en toma ambulatoria, asociada a cefalea occipital, acúfenos, fosfenos y visión borrosa.",
                "frecuenciaCardiaca": 98,
                "frecuenciaRespiratoria": 18,
                "presionSistolica": 170,
                "presionDiastolica": 105,
                "temperatura": 36.5,
                "saturacionOxigeno": 98.0,
                "clasificacionTriage": "II",
                "entornoAtencion": "01",
                "modalidadEntrega": "01",
                "viaIngreso": "01"
            },
            "consultation": {
                "diagnosticoEgreso": {
                    "codigo": "I10",
                    "descripcion": "Hipertensión esencial (primaria)",
                    "tipo": "Principal"
                },
                "diagnosticoRel1": {
                    "codigo": "R51",
                    "descripcion": "Cefalea",
                    "tipo": "Relacionado"
                },
                "diagnosticoRel2": None,
                "medicamentos": [
                    {
                        "descripcion": "Losartán Potásico 50mg tabletas",
                        "dosis": "50 mg",
                        "viaAdministracion": "01",
                        "frecuencia": "Cada 12 horas",
                        "diasTratamiento": 90,
                        "unidadesAplicadas": 180
                    }
                ],
                "condicionSalida": "01",
                "zonaResidencia": "01",
                "direccionResidencia": "Carrera 18 # 32 - 12, Sincelejo"
            }
        },
        
        # --- NODO 2: BOGOTÁ (4_000_000_000 <= documento < 7_000_000_000) ---
        {
            "demographics": {
                "tipoDocumento": "CC",
                "numeroDocumento": "4509182736",
                "paisNacionalidad": "CO",
                "nombreCompleto": "Juan Sebastián Pérez Martínez",
                "fechaNacimiento": "1995-11-23",
                "edad": 30,
                "unidadEdad": "1",
                "sexo": "male",
                "genero": "Masculino",
                "ocupacion": "Ingeniero de Sistemas",
                "voluntadAnticipada": "false",
                "categoriaDiscapacidad": "",
                "paisResidencia": "CO",
                "municipioResidencia": "11001",
                "etnia": "Ninguna"
            },
            "triage": {
                "causaAtencion": "Dolor abdominal agudo localizado en fosa ilíaca derecha de 12 horas de evolución, con irradiación lumbar, acompañado de náuseas, vómito de contenido alimenticio y picos febriles no cuantificados.",
                "frecuenciaCardiaca": 94,
                "frecuenciaRespiratoria": 20,
                "presionSistolica": 115,
                "presionDiastolica": 75,
                "temperatura": 38.4,
                "saturacionOxigeno": 97.0,
                "clasificacionTriage": "III",
                "entornoAtencion": "01",
                "modalidadEntrega": "01",
                "viaIngreso": "01"
            },
            "consultation": {
                "diagnosticoEgreso": {
                    "codigo": "K35.8",
                    "descripcion": "Apendicitis aguda, otra y la no especificada",
                    "tipo": "Principal"
                },
                "diagnosticoRel1": {
                    "codigo": "R11",
                    "descripcion": "Náuseas y vómitos",
                    "tipo": "Relacionado"
                },
                "diagnosticoRel2": {
                    "codigo": "R50.9",
                    "descripcion": "Fiebre, no especificada",
                    "tipo": "Relacionado"
                },
                "medicamentos": [
                    {
                        "descripcion": "Hioscina N-Butilbromuro 20mg/mL",
                        "dosis": "20 mg",
                        "viaAdministracion": "02",
                        "frecuencia": "Cada 8 horas en caso de dolor",
                        "diasTratamiento": 3,
                        "unidadesAplicadas": 9
                    }
                ],
                "condicionSalida": "01",
                "zonaResidencia": "01",
                "direccionResidencia": "Calle 145 # 45 - 28, Bogotá"
            }
        },
        {
            "demographics": {
                "tipoDocumento": "CC",
                "numeroDocumento": "5827364519",
                "paisNacionalidad": "CO",
                "nombreCompleto": "Ana Sofía Gómez Vásquez",
                "fechaNacimiento": "2000-02-05",
                "edad": 26,
                "unidadEdad": "1",
                "sexo": "female",
                "genero": "Femenino",
                "ocupacion": "Estudiante Universitario",
                "voluntadAnticipada": "false",
                "categoriaDiscapacidad": "",
                "paisResidencia": "CO",
                "municipioResidencia": "11001",
                "etnia": "Ninguna"
            },
            "triage": {
                "causaAtencion": "Paciente presenta cuadro de diarrea profusa y líquida de 8 episodios al día, acompañado de dolor tipo cólico abdominal difuso, signos leves de deshidratación mucosa y astenia.",
                "frecuenciaCardiaca": 88,
                "frecuenciaRespiratoria": 16,
                "presionSistolica": 105,
                "presionDiastolica": 65,
                "temperatura": 37.2,
                "saturacionOxigeno": 99.0,
                "clasificacionTriage": "IV",
                "entornoAtencion": "01",
                "modalidadEntrega": "01",
                "viaIngreso": "01"
            },
            "consultation": {
                "diagnosticoEgreso": {
                    "codigo": "A09",
                    "descripcion": "Diarrea y gastroenteritis de presunto origen infeccioso",
                    "tipo": "Principal"
                },
                "diagnosticoRel1": {
                    "codigo": "R10.4",
                    "descripcion": "Otros dolores abdominales y los no especificados",
                    "tipo": "Relacionado"
                },
                "diagnosticoRel2": None,
                "medicamentos": [
                    {
                        "descripcion": "Suero Oral de Rehidratación 60mEq",
                        "dosis": "1 sobre",
                        "viaAdministracion": "01",
                        "frecuencia": "Después de cada deposición diarreica",
                        "diasTratamiento": 3,
                        "unidadesAplicadas": 10
                    }
                ],
                "condicionSalida": "01",
                "zonaResidencia": "01",
                "direccionResidencia": "Avenida Carrera 30 # 63 - 45, Bogotá"
            }
        },
        
        # --- NODO 3: MEDELLÍN (documento >= 7_000_000_000) ---
        {
            "demographics": {
                "tipoDocumento": "CC",
                "numeroDocumento": "7102938475",
                "paisNacionalidad": "CO",
                "nombreCompleto": "Luis Eduardo Martínez López",
                "fechaNacimiento": "1960-07-30",
                "edad": 65,
                "unidadEdad": "1",
                "sexo": "male",
                "genero": "Masculino",
                "ocupacion": "Pensionado",
                "voluntadAnticipada": "false",
                "categoriaDiscapacidad": "",
                "paisResidencia": "CO",
                "municipioResidencia": "05001",
                "etnia": "Mestizo"
            },
            "triage": {
                "causaAtencion": "Paciente con lumbalgia crónica de 1 mes de evolución que se exacerba tras esfuerzo físico. No signos de alarma ni parestesias en miembros inferiores.",
                "frecuenciaCardiaca": 72,
                "frecuenciaRespiratoria": 15,
                "presionSistolica": 120,
                "presionDiastolica": 80,
                "temperatura": 36.2,
                "saturacionOxigeno": 98.0,
                "clasificacionTriage": "V",
                "entornoAtencion": "01",
                "modalidadEntrega": "01",
                "viaIngreso": "01"
            },
            "consultation": {
                "diagnosticoEgreso": {
                    "codigo": "M54.5",
                    "descripcion": "Lumbago no especificado",
                    "tipo": "Principal"
                },
                "diagnosticoRel1": None,
                "diagnosticoRel2": None,
                "medicamentos": [
                    {
                        "descripcion": "Acetaminofén 500mg tabletas",
                        "dosis": "500 mg",
                        "viaAdministracion": "01",
                        "frecuencia": "Cada 8 horas si presenta dolor",
                        "diasTratamiento": 5,
                        "unidadesAplicadas": 15
                    }
                ],
                "condicionSalida": "01",
                "zonaResidencia": "01",
                "direccionResidencia": "Diagonal 75B # 32A - 15, Medellín"
            }
        },
        {
            "demographics": {
                "tipoDocumento": "CC",
                "numeroDocumento": "8293847561",
                "paisNacionalidad": "CO",
                "nombreCompleto": "Diana Laura Vásquez Ruiz",
                "fechaNacimiento": "1982-12-14",
                "edad": 43,
                "unidadEdad": "1",
                "sexo": "female",
                "genero": "Femenino",
                "ocupacion": "Profesora de Primaria",
                "voluntadAnticipada": "false",
                "categoriaDiscapacidad": "",
                "paisResidencia": "CO",
                "municipioResidencia": "05001",
                "etnia": "Ninguna"
            },
            "triage": {
                "causaAtencion": "Cuadro clínico de 3 días de evolución caracterizado por tos productiva con expectoración mucopurulenta, fiebre cuantificada en 38.8°C, escalofríos y dificultad respiratoria leve a moderada.",
                "frecuenciaCardiaca": 105,
                "frecuenciaRespiratoria": 22,
                "presionSistolica": 110,
                "presionDiastolica": 70,
                "temperatura": 38.8,
                "saturacionOxigeno": 94.0,
                "clasificacionTriage": "III",
                "entornoAtencion": "01",
                "modalidadEntrega": "01",
                "viaIngreso": "01"
            },
            "consultation": {
                "diagnosticoEgreso": {
                    "codigo": "J18.9",
                    "descripcion": "Neumonía, no especificada",
                    "tipo": "Principal"
                },
                "diagnosticoRel1": {
                    "codigo": "J45.9",
                    "descripcion": "Asma, no especificada",
                    "tipo": "Relacionado"
                },
                "diagnosticoRel2": {
                    "codigo": "R05",
                    "descripcion": "Tos",
                    "tipo": "Relacionado"
                },
                "medicamentos": [
                    {
                        "descripcion": "Amoxicilina 500mg cápsulas",
                        "dosis": "500 mg",
                        "viaAdministracion": "01",
                        "frecuencia": "Cada 8 horas",
                        "diasTratamiento": 7,
                        "unidadesAplicadas": 21
                    }
                ],
                "condicionSalida": "01",
                "zonaResidencia": "01",
                "direccionResidencia": "Calle 49 # 70 - 22, Medellín"
            }
        }
    ]

    for idx, p in enumerate(patients, 1):
        print(f"\n👤 [{idx}/6] Sembrando paciente: {p['demographics']['nombreCompleto']}...")
        
        # 1. Registrar paciente
        p_res = requests.post(f"{BASE_URL}/api/v1/fhir/patient", headers=headers, json=p["demographics"])
        if p_res.status_code != 200:
            print(f"   ❌ Error al registrar paciente: {p_res.text}")
            continue
        p_data = p_res.json()
        p_id = p_data["patient_id"]
        print(f"   ✅ Paciente creado con ID FHIR: {p_id}")
        
        # 2. Registrar triage
        triage_payload = p["triage"]
        triage_payload["patientId"] = p_id
        triage_payload["documento"] = p["demographics"]["numeroDocumento"]
        t_res = requests.post(f"{BASE_URL}/api/v1/fhir/triage", headers=headers, json=triage_payload)
        if t_res.status_code != 200:
            print(f"   ❌ Error al registrar triage: {t_res.text}")
            continue
        t_data = t_res.json()
        enc_id = t_data["encounter_id"]
        print(f"   ✅ Triage/Signos Vitales creados. ID Encuentro: {enc_id}")
        
        # 3. Registrar consulta/egreso
        consultation_payload = p["consultation"]
        consultation_payload["patientId"] = p_id
        consultation_payload["documento"] = p["demographics"]["numeroDocumento"]
        consultation_payload["encounterId"] = enc_id
        c_res = requests.post(f"{BASE_URL}/api/v1/fhir/consultation", headers=headers, json=consultation_payload)
        if c_res.status_code != 200:
            print(f"   ❌ Error al registrar consulta médica: {c_res.text}")
            continue
        print("   ✅ Consulta médica y egreso clínico registrados con éxito.")
        
    print("\n✨ Proceso de sembrado de datos finalizado con éxito. ¡Tablas e instancias FHIR pobladas!")

if __name__ == "__main__":
    seed()
