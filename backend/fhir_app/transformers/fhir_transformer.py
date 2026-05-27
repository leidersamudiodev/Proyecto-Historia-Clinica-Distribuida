# backend/fhir_app/transformers/fhir_transformer.py
from fhir.resources.R4B.patient import Patient
from fhir.resources.R4B.identifier import Identifier
from fhir.resources.R4B.humanname import HumanName
from fhir.resources.R4B.address import Address
from fhir.resources.R4B.extension import Extension
from fhir.resources.R4B.codeableconcept import CodeableConcept
from fhir.resources.R4B.coding import Coding
from fhir.resources.R4B.encounter import Encounter
from fhir.resources.R4B.observation import Observation, ObservationComponent
from fhir.resources.R4B.condition import Condition
from fhir.resources.R4B.medicationrequest import MedicationRequest
from datetime import datetime, date
from typing import Dict, Any, List, Union


class FHIRTransformer:
    """Transforma datos de HC colombiana a recursos FHIR R4"""
    
    @staticmethod
    def to_fhir_patient(data: Dict[str, Any]) -> Patient:
        """
        Transforma datos de identificación a recurso FHIR Patient
        
        Args:
            data: Diccionario con los 15 campos de identificación
            
        Returns:
            Patient: Recurso FHIR Patient
        """
        
        # Crear identificador principal (documento de identidad)
        identifier = Identifier(
            system="http://www.minsalud.gov.co/identificacion",
            value=data["numeroDocumento"],
            type=CodeableConcept(
                coding=[Coding(
                    system="http://terminology.hl7.org/CodeSystem/v2-0203",
                    code=FHIRTransformer._map_document_type(data["tipoDocumento"]),
                    display=data["tipoDocumento"]
                )]
            )
        )
        
        # Crear nombre
        name = HumanName(
            text=data["nombreCompleto"],
            use="official"
        )
        
        # Crear dirección
        address = Address(
            use="home",
            country=data["paisResidencia"],
            city=FHIRTransformer._get_city_name(data["municipioResidencia"]),
            extension=[
                Extension(
                    url="http://hl7.org/fhir/StructureDefinition/iso21090-SC-coding",
                    valueCoding=Coding(
                        system="https://www.dane.gov.co/divipola",
                        code=data["municipioResidencia"]
                    )
                )
            ]
        )
        
        # Crear paciente
        patient = Patient(
            identifier=[identifier],
            name=[name],
            gender=data["sexo"],
            birthDate=str(data["fechaNacimiento"]),
            address=[address]
        )
        
        # Agregar extensiones opcionales
        extensions = []
        
        # Nacionalidad
        if data.get("paisNacionalidad"):
            extensions.append(Extension(
                url="http://hl7.org/fhir/StructureDefinition/patient-nationality",
                extension=[
                    Extension(
                        url="code",
                        valueCodeableConcept=CodeableConcept(
                            coding=[Coding(
                                system="urn:iso:std:iso:3166",
                                code=data["paisNacionalidad"]
                            )]
                        )
                    )
                ]
            ))
        
        # Ocupación
        if data.get("ocupacion"):
            extensions.append(Extension(
                url="http://hl7.org/fhir/StructureDefinition/patient-occupation",
                valueString=data["ocupacion"]
            ))
        
        # Etnia
        if data.get("etnia") and data["etnia"] != "Ninguna":
            extensions.append(Extension(
                url="http://hl7.org/fhir/us/core/StructureDefinition/us-core-ethnicity",
                valueCodeableConcept=CodeableConcept(
                    text=data["etnia"]
                )
            ))
        
        # Discapacidad
        if data.get("categoriaDiscapacidad"):
            extensions.append(Extension(
                url="http://hl7.org/fhir/StructureDefinition/patient-disability",
                valueCodeableConcept=CodeableConcept(
                    text=data["categoriaDiscapacidad"]
                )
            ))
        
        # Género (diferente de sexo)
        if data.get("genero"):
            extensions.append(Extension(
                url="http://hl7.org/fhir/StructureDefinition/patient-genderIdentity",
                valueCodeableConcept=CodeableConcept(
                    text=data["genero"]
                )
            ))
        
        if extensions:
            patient.extension = extensions
        
        return patient
    
    @staticmethod
    def to_fhir_encounter(data: Dict[str, Any], patient_id: str) -> Encounter:
        """Transforma datos de triage/atención a un Encounter FHIR R5 (fhir.resources v7+)"""
        class_codes = {"01": "EMER", "02": "AMB", "03": "IMP"}
        class_displays = {"01": "Urgencias", "02": "Ambulatorio", "03": "Hospitalización"}
        entorno = data.get("entornoAtencion", "01")
        triage = data.get("clasificacionTriage", "")

        extensions = [
            {"url": "http://hl7.org/fhir/StructureDefinition/encounter-associatedOrganization",
             "valueString": data.get("entidadSalud", "No especificado")}
        ]
        if triage:
            extensions.append({
                "url": "http://www.minsalud.gov.co/triage",
                "valueCodeableConcept": {
                    "coding": [{
                        "system": "http://www.minsalud.gov.co/CodeSystem/triage-manchester",
                        "code": triage,
                        "display": f"Triage {triage}"
                    }]
                }
            })

        # En FHIR R4B: class es un Coding simple, se usa period en vez de actualPeriod,
        # reasonCode = [{text:...}] en vez de reason
        enc_dict = {
            "resourceType": "Encounter",
            "status": "in-progress",
            "class_fhir": {
                "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
                "code": class_codes.get(entorno, "EMER"),
                "display": class_displays.get(entorno, "Urgencias")
            },
            "subject": {"reference": f"Patient/{patient_id}"},
            "reasonCode": [{"text": data["causaAtencion"]}],
            "period": {"start": datetime.now().isoformat()},
            "extension": extensions
        }
        # In fhir.resources, 'class' is a python reserved keyword so it's aliased.
        # We can map it by renaming class_fhir to class before parsing or passing directly if supported,
        # but the safest way via dict is to just use 'class':
        enc_dict["class"] = enc_dict.pop("class_fhir")
        
        return Encounter.parse_obj(enc_dict)

        
    @staticmethod
    def to_fhir_observation(data: Dict[str, Any], patient_id: str, encounter_id: str) -> Observation:
        """Transforma signos vitales de triage a un panel Observation FHIR R4 con LOINC codes"""
        obs_dict = {
            "resourceType": "Observation",
            "status": "final",
            "category": [{
                "coding": [{
                    "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                    "code": "vital-signs",
                    "display": "Vital Signs"
                }]
            }],
            "code": {
                "coding": [{
                    "system": "http://loinc.org",
                    "code": "85353-1",
                    "display": "Vital signs panel"
                }],
                "text": "Panel de Signos Vitales y Triage"
            },
            "subject": {"reference": f"Patient/{patient_id}"},
            "encounter": {"reference": f"Encounter/{encounter_id}"},
            "effectiveDateTime": datetime.now().isoformat(),
            "component": [
                {
                    "code": {"coding": [{"system": "http://loinc.org", "code": "8867-4", "display": "Heart rate"}]},
                    "valueQuantity": {"value": float(data["frecuenciaCardiaca"]), "unit": "bpm",
                                      "system": "http://unitsofmeasure.org", "code": "/min"}
                },
                {
                    "code": {"coding": [{"system": "http://loinc.org", "code": "9279-1", "display": "Respiratory rate"}]},
                    "valueQuantity": {"value": float(data["frecuenciaRespiratoria"]), "unit": "rpm",
                                      "system": "http://unitsofmeasure.org", "code": "/min"}
                },
                {
                    "code": {"coding": [{"system": "http://loinc.org", "code": "8310-5", "display": "Body temperature"}]},
                    "valueQuantity": {"value": float(data["temperatura"]), "unit": "Cel",
                                      "system": "http://unitsofmeasure.org", "code": "Cel"}
                },
                {
                    "code": {"coding": [{"system": "http://loinc.org", "code": "8480-6", "display": "Systolic blood pressure"}]},
                    "valueQuantity": {"value": float(data["presionSistolica"]), "unit": "mmHg",
                                      "system": "http://unitsofmeasure.org", "code": "mm[Hg]"}
                },
                {
                    "code": {"coding": [{"system": "http://loinc.org", "code": "8462-4", "display": "Diastolic blood pressure"}]},
                    "valueQuantity": {"value": float(data["presionDiastolica"]), "unit": "mmHg",
                                      "system": "http://unitsofmeasure.org", "code": "mm[Hg]"}
                }
            ]
        }
        # Agregar SpO2 si está presente
        if data.get("saturacionOxigeno") is not None:
            obs_dict["component"].append({
                "code": {"coding": [{"system": "http://loinc.org", "code": "59408-5", "display": "Oxygen saturation"}]},
                "valueQuantity": {"value": float(data["saturacionOxigeno"]), "unit": "%",
                                  "system": "http://unitsofmeasure.org", "code": "%"}
            })
        # Agregar peso si está presente
        if data.get("pesoKg") is not None:
            obs_dict["component"].append({
                "code": {"coding": [{"system": "http://loinc.org", "code": "29463-7", "display": "Body weight"}]},
                "valueQuantity": {"value": float(data["pesoKg"]), "unit": "kg",
                                  "system": "http://unitsofmeasure.org", "code": "kg"}
            })
        # Agregar talla si está presente
        if data.get("tallaCm") is not None:
            obs_dict["component"].append({
                "code": {"coding": [{"system": "http://loinc.org", "code": "8302-2", "display": "Body height"}]},
                "valueQuantity": {"value": float(data["tallaCm"]), "unit": "cm",
                                  "system": "http://unitsofmeasure.org", "code": "cm"}
            })
        return Observation.parse_obj(obs_dict)

    @staticmethod
    def to_fhir_condition(diagnostico: Any, patient_id: str, encounter_id: str, asserter_name: str = None) -> Condition:
        """
        Crea un recurso Condition FHIR R4 para un diagnóstico CIE-10.
        Acepta:
          - dict con keys: codigo, descripcion, tipo (de DiagnosticoData)
          - str con código CIE-10 (compatibilidad hacia atrás)
        """
        # Normalizar entrada
        if isinstance(diagnostico, dict):
            cie10_code = diagnostico.get("codigo", "")
            display_name = diagnostico.get("descripcion") or f"Diagnóstico CIE-10: {cie10_code}"
            tipo = diagnostico.get("tipo", "Principal")
        elif isinstance(diagnostico, str):
            cie10_code = diagnostico
            display_name = f"Diagnóstico CIE-10: {cie10_code}"
            tipo = "Principal"
        else:
            raise ValueError(f"diagnostico debe ser str o dict, no {type(diagnostico)}")

        # Mapeo CIE-10 común colombiano
        cie10_display_map = {
            "J00": "Rinofaringitis aguda (resfriado común)",
            "J18.9": "Neumonía, no especificada",
            "I10": "Hipertensión esencial (primaria)",
            "E11.9": "Diabetes mellitus tipo 2 sin complicaciones",
            "K29.7": "Gastritis, no especificada",
            "M54.5": "Dolor lumbar",
            "A09": "Gastroenteritis infecciosa",
            "K37": "Apendicitis no especificada",
            "R10.4": "Otros dolores abdominales y los no especificados",
            "J06.9": "Infección aguda de las vías respiratorias superiores",
            "K30": "Dispepsia funcional"
        }
        if display_name == f"Diagnóstico CIE-10: {cie10_code}":
            display_name = cie10_display_map.get(cie10_code, display_name)

        # Categorías por tipo de diagnóstico
        category_map = {
            "Principal": ("encounter-diagnosis", "Encounter Diagnosis"),
            "Relacionado": ("encounter-diagnosis", "Diagnóstico Relacionado"),
            "Complicación": ("encounter-diagnosis", "Complicación")
        }
        cat_code, cat_display = category_map.get(tipo, ("encounter-diagnosis", tipo))

        cond_dict = {
            "resourceType": "Condition",
            "clinicalStatus": {
                "coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                            "code": "active", "display": "Active"}]
            },
            "verificationStatus": {
                "coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-ver-status",
                            "code": "confirmed", "display": "Confirmed"}]
            },
            "category": [{
                "coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-category",
                            "code": cat_code, "display": cat_display}],
                "text": tipo
            }],
            "code": {
                "coding": [{"system": "http://hl7.org/fhir/sid/icd-10",
                            "code": cie10_code, "display": display_name}],
                "text": display_name
            },
            "subject": {"reference": f"Patient/{patient_id}"},
            "encounter": {"reference": f"Encounter/{encounter_id}"},
            "recordedDate": datetime.now().date().isoformat()
        }
        
        if asserter_name:
            cond_dict["asserter"] = {"display": asserter_name}
            
        return Condition.parse_obj(cond_dict)

    @staticmethod
    def to_fhir_medication_request(med: Dict[str, Any], patient_id: str, encounter_id: str) -> MedicationRequest:
        """Crea un recurso MedicationRequest FHIR R4 usando parse_obj()"""
        # Acepta viaAdministracion como código (01-05) o texto libre (oral, IV, etc.)
        route_map = {"01": "Oral", "02": "Intravenosa", "03": "Intramuscular", "04": "Subcutánea", "05": "Tópica"}
        via_raw = med.get("viaAdministracion", "oral")
        route_text = route_map.get(via_raw, via_raw.capitalize() if via_raw else "Oral")
        dias = med.get("diasTratamiento", 7)
        unidades = med.get("unidadesAplicadas", 1)

        med_dict = {
            "resourceType": "MedicationRequest",
            "status": "active",
            "intent": "order",
            "medicationCodeableConcept": {"text": med["descripcion"]},
            "subject": {"reference": f"Patient/{patient_id}"},
            "encounter": {"reference": f"Encounter/{encounter_id}"},
            "authoredOn": datetime.now().date().isoformat(),
            "dosageInstruction": [{
                "text": f"{med['dosis']} - Vía: {route_text} - Frecuencia: {med['frecuencia']} por {dias} días",
                "timing": {"repeat": {"duration": float(dias), "durationUnit": "d"}},
                "route": {"text": route_text}
            }],
            "extension": [{
                "url": "http://hl7.org/fhir/StructureDefinition/medicationrequest-quantity",
                "valueString": f"{unidades} unidades"
            }]
        }
        return MedicationRequest.parse_obj(med_dict)


    @staticmethod
    def _map_document_type(tipo: str) -> str:
        """Mapea tipos de documento colombianos a códigos FHIR"""
        mapping = {
            "CC": "DL",  # Driver's License (usado para cédula)
            "TI": "PPN", # Passport Number (usado para TI)
            "CE": "PPN", # Passport Number
            "PA": "PPN", # Passport
            "RC": "MR",  # Medical Record Number
            "MS": "AN",  # Account Number
            "AS": "AN"   # Account Number
        }
        return mapping.get(tipo, "DL")
    
    @staticmethod
    def _get_city_name(codigo_dane: str) -> str:
        """Obtiene el nombre de la ciudad desde el código DANE"""
        cities = {
            "11001": "Bogotá D.C.",
            "05001": "Medellín",
            "76001": "Cali",
            "08001": "Barranquilla",
            "13001": "Cartagena",
            "68001": "Bucaramanga",
            "66001": "Pereira",
            "17001": "Manizales",
            "50001": "Villavicencio"
        }
        return cities.get(codigo_dane, "Desconocida")
