# backend/fhir_app/models/clinical_models.py
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class TriageData(BaseModel):
    """Modelo para registro de triage y signos vitales (Observation + Encounter)"""
    patientId: str = Field(..., description="ID del paciente en FHIR")
    documento: str = Field(..., description="Número de documento del paciente para ruteo distribuido")
    entidadSalud: str = Field(default="EPS Sanitas", description="Entidad de salud")
    causaAtencion: str = Field(..., description="Motivo de la consulta / Causa de la atención")
    entornoAtencion: str = Field(default="01", description="01=Urgencias, 02=Consulta Externa, etc.")
    modalidadEntrega: str = Field(default="01", description="01=Intramural, 03=Telemedicina")
    viaIngreso: str = Field(default="01", description="01=Espontánea, 02=Remitido")

    # Signos vitales para Observation FHIR
    frecuenciaCardiaca: int = Field(..., ge=20, le=250, description="Frecuencia cardíaca (bpm)")
    frecuenciaRespiratoria: int = Field(..., ge=5, le=80, description="Frecuencia respiratoria (rpm)")
    presionSistolica: int = Field(..., ge=40, le=300, description="Presión arterial sistólica (mmHg)")
    presionDiastolica: int = Field(..., ge=20, le=200, description="Presión arterial diastólica (mmHg)")
    temperatura: float = Field(..., ge=30.0, le=45.0, description="Temperatura corporal (°C)")
    saturacionOxigeno: Optional[float] = Field(None, ge=50.0, le=100.0, description="SpO2 (%)")
    pesoKg: Optional[float] = Field(None, ge=0.5, le=500.0, description="Peso corporal (kg)")
    tallaCm: Optional[float] = Field(None, ge=10.0, le=300.0, description="Talla (cm)")

    # Clasificación y fecha
    clasificacionTriage: str = Field(default="III", description="Manchester: I, II, III, IV, V")
    fechaTriage: Optional[str] = Field(None, description="Fecha/hora del triage ISO8601")


class DiagnosticoData(BaseModel):
    """Modelo para un diagnóstico CIE-10"""
    codigo: str = Field(..., description="Código CIE-10 (ej: K37)")
    descripcion: str = Field(..., description="Descripción del diagnóstico")
    tipo: str = Field(default="Principal", description="Principal, Relacionado, Complicación")


class MedicationData(BaseModel):
    """Modelo para prescripción de un medicamento en consulta"""
    descripcion: str = Field(..., description="Nombre del medicamento (ej: Acetaminofén 500mg)")
    dosis: str = Field(..., description="Dosis (ej: 500mg)")
    viaAdministracion: str = Field(default="oral", description="Vía de administración")
    frecuencia: str = Field(..., description="Frecuencia (ej: Cada 8 horas)")
    diasTratamiento: int = Field(default=7, ge=1, description="Días de tratamiento")
    unidadesAplicadas: int = Field(default=1, ge=1, description="Unidades totales")


class ConsultationData(BaseModel):
    """Modelo para consulta médica (Condition + MedicationRequest + Encounter update)"""
    patientId: str = Field(..., description="ID del paciente en FHIR")
    documento: str = Field(..., description="Número de documento del paciente para ruteo distribuido")
    encounterId: str = Field(..., description="ID del encuentro clínico en FHIR")
    medicoResponsable: str = Field(default="Dr. Carlos Rodríguez", description="Médico tratante")
    codigoPrestador: str = Field(default="110010001234", description="Código de habilitación IPS")

    # Diagnósticos (CIE-10) como objetos estructurados
    diagnosticoEgreso: DiagnosticoData = Field(..., description="Diagnóstico Principal de egreso (CIE-10)")
    diagnosticoRel1: Optional[DiagnosticoData] = Field(None, description="Diagnóstico Relacionado 1")
    diagnosticoRel2: Optional[DiagnosticoData] = Field(None, description="Diagnóstico Relacionado 2")

    # Medicamentos opcionales
    medicamentos: List[MedicationData] = Field(default=[], description="Lista de medicamentos prescritos")

    # Egreso
    condicionSalida: str = Field(default="01", description="01=Vivo, 02=Muerto")
    direccionResidencia: str = Field(default="Calle 123 #45-67", description="Dirección actual")
    zonaResidencia: str = Field(default="01", description="01=Urbana, 02=Rural")
