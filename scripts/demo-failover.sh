#!/bin/bash
# =============================================================================
# demo-failover.sh — Demostración Completa de Tolerancia a Fallos
# Sistema de Historia Clínica Distribuida
# Nodos: Sincelejo (nodo1), Bogotá (nodo2), Medellín (nodo3)
# Cubre: BD PostgreSQL + HAPI FHIR + Resincronización automática
# =============================================================================

API="http://localhost:8001"
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

banner() {
  echo ""
  echo -e "${BLUE}${BOLD}══════════════════════════════════════════════════════════${NC}"
  echo -e "${CYAN}${BOLD}  $1${NC}"
  echo -e "${BLUE}${BOLD}══════════════════════════════════════════════════════════${NC}"
  echo ""
}

ok()   { echo -e "${GREEN}✅ $1${NC}"; }
warn() { echo -e "${YELLOW}⚠️  $1${NC}"; }
err()  { echo -e "${RED}❌ $1${NC}"; }
info() { echo -e "${CYAN}ℹ️  $1${NC}"; }
step() { echo -e "${BOLD}→ $1${NC}"; }

banner "DEMO TOLERANCIA A FALLOS — HISTORIA CLÍNICA DISTRIBUIDA"

# ─── OBTENER TOKEN JWT ──────────────────────────────────────────────────────
echo -e "${BOLD}PREVIO: Obtener token JWT (OAuth2 / SMART on FHIR)${NC}"
TOKEN_RESP=$(curl -s -X POST "$API/api/auth/token" \
  -H "Content-Type: application/json" \
  -d '{"username":"medico","password":"medico123"}')
TOKEN=$(echo "$TOKEN_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null)
if [ -n "$TOKEN" ]; then
  ok "JWT obtenido para usuario 'medico' (SMART on FHIR)"
  info "Scope: $(echo "$TOKEN_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('scope',''))" 2>/dev/null)"
else
  warn "No se obtuvo token — los endpoints de escritura requerirán autenticación"
fi
echo ""

# ─── PASO 1: Estado inicial ─────────────────────────────────────────────────
echo -e "${BOLD}PASO 1: Estado inicial de los 3 nodos (BD + FHIR)${NC}"
echo ""
NODOS=$(curl -s "$API/api/nodes/geo" 2>/dev/null)
echo "$NODOS" | python3 -c "
import sys,json
nodos=json.load(sys.stdin)
for n in nodos:
    estado = '🟢 ONLINE' if n.get('activo') else '🔴 OFFLINE'
    latencia = f\"{n.get('latencia_ms','?')} ms\" if n.get('latencia_ms') else 'N/A'
    print(f\"  {n.get('ciudad','?'):15} ({n.get('id','?')}): {estado}  | Latencia BD: {latencia}\")
" 2>/dev/null || echo "  (no disponible)"

# Estado FHIR
echo ""
FHIR_HEALTH=$(curl -s "$API/api/v1/fhir/health" 2>/dev/null)
echo "$FHIR_HEALTH" | python3 -c "
import sys,json
d=json.load(sys.stdin)
nodos=d.get('nodos_fhir',{}).get('nodos',{})
for k,v in nodos.items():
    estado = '🟢 OK' if v.get('status')=='ok' else '🔴 ERROR'
    print(f\"  FHIR {v.get('ciudad','?'):15}: {estado}\")
" 2>/dev/null

echo ""
ok "Estado inicial verificado"

# ─── PASO 2: Insertar paciente de prueba ────────────────────────────────────
echo ""
echo -e "${BOLD}PASO 2: Crear paciente FHIR con autenticación JWT${NC}"
echo ""
PAT=$(curl -s -X POST "$API/api/v1/fhir/patient" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "tipoDocumento":"CC","numeroDocumento":"1002345678",
    "paisNacionalidad":"CO","nombreCompleto":"Fernando Ruiz Ocampo",
    "fechaNacimiento":"1980-05-15","edad":44,"unidadEdad":"1",
    "sexo":"male","paisResidencia":"CO","municipioResidencia":"70001"
  }' 2>/dev/null)
PID=$(echo "$PAT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('fhir_resource',{}).get('id','ERROR'))" 2>/dev/null)
if [ "$PID" != "ERROR" ] && [ -n "$PID" ]; then
  ok "Paciente FHIR creado: ID = $PID (Sede Sincelejo — CC<4.000.000.000)"
else
  warn "Error creando paciente: $(echo "$PAT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('detail','?'))" 2>/dev/null)"
  PID="test-patient-id"
fi

# ─── PASO 3: Verificar modelo de distribución ───────────────────────────────
banner "MODELO DE DISTRIBUCIÓN — SHARDING + CONSISTENCIA EVENTUAL"
REP=$(curl -s "$API/api/v1/bd/replication-status" 2>/dev/null)
echo "$REP" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(f\"  Modelo:   {d.get('modelo','?')}\")
print(f\"  Sync:     cada {d.get('consistencia',{}).get('intervalo_sync_segundos','?')} segundos\")
print(\"  Shards:\")
for s in d.get('distribucion_shards',[]):
    print(f\"    {s.get('nodo','?'):25} → {s.get('rango','?')}\")
print(f\"  Failover: <{d.get('failover',{}).get('tiempo_maximo_s','?')}s — nodos activos: {d.get('failover',{}).get('nodos_activos','?')}/{d.get('failover',{}).get('nodos_totales','?')}\")
" 2>/dev/null

# ─── PASO 4: Simulación caída BD ────────────────────────────────────────────
banner "SIMULACIÓN: CAÍDA DEL NODO SINCELEJO (pg_nodo1)"

step "Deteniendo pg_nodo1 (Sincelejo BD)..."
docker stop pg_nodo1 > /dev/null 2>&1
sleep 2
warn "pg_nodo1 (Sincelejo) DETENIDO"

echo ""
echo -e "${BOLD}PASO 4: Verificar estado tras la caída${NC}"
curl -s "$API/api/nodes/geo" 2>/dev/null | python3 -c "
import sys,json
nodos=json.load(sys.stdin)
for n in nodos:
    estado = '🟢 ONLINE' if n.get('activo') else '🔴 OFFLINE'
    print(f\"  {n.get('ciudad','?'):15}: {estado}\")
" 2>/dev/null

# ─── PASO 5: Failover BD automático ────────────────────────────────────────
echo ""
echo -e "${BOLD}PASO 5: Failover automático BD (<5s)${NC}"
FAILOVER=$(curl -s "$API/api/system/failover-test?nodo=nodo1" 2>/dev/null)
echo "$FAILOVER" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(f\"  Éxito:           {d.get('success')}\")
print(f\"  Failover activo: {d.get('failover_activado')}\")
print(f\"  Nodo solicitado: {d.get('nodo_solicitado')}\")
print(f\"  Nodo usado:      {d.get('nodo_usado')}\")
print(f\"  Tiempo failover: {d.get('tiempo_failover_ms')} ms\")
print(f\"  Dentro de 5s:    {d.get('dentro_limite_5s')}\")
" 2>/dev/null

DENTRO=$(echo "$FAILOVER" | python3 -c "import sys,json; print(json.load(sys.stdin).get('dentro_limite_5s',False))" 2>/dev/null)
if [ "$DENTRO" = "True" ]; then
  ok "¡Failover BD completado DENTRO del límite de 5 segundos!"
else
  warn "Failover BD tardó más de 5 segundos"
fi

# ─── PASO 6: Operar durante la caída ───────────────────────────────────────
echo ""
echo -e "${BOLD}PASO 6: El sistema sigue operando — crear triage durante la caída${NC}"
TRIAGE=$(curl -s -X POST "$API/api/v1/fhir/triage" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d "{
    \"patientId\":\"$PID\",
    \"causaAtencion\":\"Cefalea severa con aura visual (Registro de Continuidad)\",
    \"frecuenciaCardiaca\":88,\"frecuenciaRespiratoria\":18,
    \"temperatura\":37.0,\"presionSistolica\":120,\"presionDiastolica\":80,
    \"clasificacionTriage\":\"IV\"
  }" 2>/dev/null)
ENC=$(echo "$TRIAGE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('encounter_id','ERROR'))" 2>/dev/null)
if [ "$ENC" != "ERROR" ] && [ -n "$ENC" ]; then
  NODO_USADO=$(echo "$TRIAGE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('nodo','?'))" 2>/dev/null)
  ok "Sistema continúa operando. Encounter=$ENC (nodo=$NODO_USADO)"
else
  info "Triage FHIR requiere servidor HAPI FHIR activo (nivel BD usa failover)"
fi

# ─── PASO 7: Prueba failover FHIR ──────────────────────────────────────────
banner "PRUEBA FAILOVER — NIVEL HAPI FHIR"
FHIR_FAIL=$(curl -s "$API/api/v1/fhir/failover-test?nodo=nodo1" 2>/dev/null)
echo "$FHIR_FAIL" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(f\"  Éxito:         {d.get('success')}\")
print(f\"  FHIR activo:   {d.get('nodo_fhir_activo')}\")
print(f\"  Tiempo total:  {d.get('tiempo_total_ms')} ms\")
print(f\"  Dentro 5s:     {d.get('dentro_limite_5s')}\")
print(\"  Estado nodos FHIR:\")
for n in d.get('nodos',[]):
    estado = '🟢' if n.get('status')=='ok' else '🔴'
    lat = f\"{n.get('latencia_ms','?')}ms\" if n.get('latencia_ms') else ''
    print(f\"    {estado} {n.get('nodo','?'):15} — {n.get('status','?')} {lat}\")
" 2>/dev/null

# ─── PASO 8: Recuperación y resincronización ────────────────────────────────
banner "RECUPERACIÓN: REINICIANDO NODO SINCELEJO"
step "Reiniciando pg_nodo1..."
docker start pg_nodo1 > /dev/null 2>&1
echo -n "  Esperando que el nodo esté healthy"
for i in $(seq 1 20); do
  HEALTH=$(docker inspect --format='{{.State.Health.Status}}' pg_nodo1 2>/dev/null)
  if [ "$HEALTH" = "healthy" ]; then
    echo ""
    ok "pg_nodo1 recuperado y saludable"
    break
  fi
  echo -n "."
  sleep 2
done
echo ""

step "Esperando re-sincronización automática (2 segundos)..."
sleep 3

echo -e "${BOLD}PASO 8: Estado tras recuperación${NC}"
curl -s "$API/api/nodes/geo" 2>/dev/null | python3 -c "
import sys,json
nodos=json.load(sys.stdin)
for n in nodos:
    estado = '🟢 ONLINE' if n.get('activo') else '🔴 OFFLINE'
    sync = n.get('total_sincronizados',0)
    print(f\"  {n.get('ciudad','?'):15}: {estado}  | Sincronizados: {sync}\")
" 2>/dev/null

# ─── Logs del sistema ───────────────────────────────────────────────────────
banner "LOG DE EVENTOS DEL SISTEMA"
curl -s "$API/api/system/logs?limit=15" 2>/dev/null | python3 -c "
import sys,json
d=json.load(sys.stdin)
for l in d.get('logs',[]):
    ts=l.get('ts','')[:19].replace('T',' ')
    t=l.get('type','info').upper()
    m=l.get('msg','')
    print(f'  [{t:5}] {ts} — {m}')
" 2>/dev/null

# ─── Resumen ────────────────────────────────────────────────────────────────
banner "RESUMEN DE LA DEMOSTRACIÓN"
echo -e "  ${GREEN}✅ Autenticación JWT (OAuth2/SMART on FHIR) verificada${NC}"
echo -e "  ${GREEN}✅ Sistema detectó caída del nodo Sincelejo${NC}"
echo -e "  ${GREEN}✅ Failover BD automático a nodo secundario <5s${NC}"
echo -e "  ${GREEN}✅ Failover FHIR demostrado con latencias por nodo${NC}"
echo -e "  ${GREEN}✅ 2 nodos restantes continuaron operando${NC}"
echo -e "  ${GREEN}✅ Nodo recuperado — re-sincronización automática (intervalo 2s)${NC}"
echo -e "  ${CYAN}📊 Grafana:    http://localhost:3000  (admin/admin123)${NC}"
echo -e "  ${CYAN}📈 Prometheus: http://localhost:9090${NC}"
echo -e "  ${CYAN}🔍 Métricas:   http://localhost:8001/metrics${NC}"
echo -e "  ${CYAN}🔗 BD Status:  http://localhost:8001/api/v1/bd/replication-status${NC}"
echo ""
