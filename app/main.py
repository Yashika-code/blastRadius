"""
FastAPI Application for BlastRadius Agent.
Provides RESTful endpoints for graph inspection, alert ingestion,
incident analysis, safe remediation, rollback, and reports.
"""
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any, List
from app.config import settings
from app.models.schemas import AlertPayload, IncidentReport
from app.graph.seed import seed_database
from app.graph.queries import get_graph_overview
from app.graph.client import falkor_client
from app.services.incident_report import incident_service

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure client verifies live FalkorDB connection on startup
    falkor_client.check_connection()
    # Seed topology on startup
    seed_database(reset=False)
    yield

app = FastAPI(
    title=settings.APP_NAME,
    description="Autonomous Infrastructure Incident Triage & Cascading Failure Remediation powered by FalkorDB",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS for dashboard interactions
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health", tags=["System"])
def health_check():
    """
    Truthful system health check. Distinguishes application availability
    from FalkorDB graph database connectivity.
    """
    status_report = falkor_client.get_status_report()
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "falkordb_connected": status_report["falkordb_connected"],
        "active_backend": status_report["active_backend"],
        "graph_name": status_report["graph_name"],
        "falkordb_host": status_report["host"],
        "falkordb_port": status_report["port"],
        "connection_error": status_report["connection_error"]
    }

@app.get("/graph/overview", tags=["Graph"])
def graph_overview():
    return get_graph_overview()

@app.post("/graph/seed", tags=["Graph"])
def trigger_seed(reset: bool = True):
    result = seed_database(reset=reset)
    return result

@app.post("/alert", tags=["Incident Triage"], response_model=IncidentReport)
def receive_alert(alert: AlertPayload):
    """
    Ingests an incoming alert and triggers autonomous graph triage pipeline.
    Validates component existence and rejects empty payloads.
    """
    if not alert.component_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Alert validation failed: 'component_name' cannot be empty."
        )
    report = incident_service.create_and_analyze(alert)
    return report

@app.post("/incidents/analyze", tags=["Incident Triage"], response_model=IncidentReport)
def analyze_incident(alert: AlertPayload):
    """
    Alias for analyzing an alert directly.
    """
    return receive_alert(alert)

@app.get("/incidents", tags=["Incident Triage"], response_model=List[IncidentReport])
def list_incidents():
    return incident_service.list_incidents()

@app.get("/incidents/{incident_id}", tags=["Incident Triage"], response_model=IncidentReport)
def get_incident(incident_id: str):
    inc = incident_service.get_incident(incident_id)
    if not inc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Incident '{incident_id}' not found.")
    return inc

@app.get("/incidents/{incident_id}/report", tags=["Incident Triage"])
def get_incident_report(incident_id: str):
    inc = incident_service.get_incident(incident_id)
    if not inc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Incident '{incident_id}' not found.")
    return inc.model_dump()

@app.post("/incidents/{incident_id}/remediate", tags=["Remediation"])
def remediate_incident(incident_id: str, payload: Dict[str, Any]):
    """
    Requires 'approved: true' to execute actions against the infrastructure simulator.
    Rejects missing or false approval.
    """
    inc = incident_service.get_incident(incident_id)
    if not inc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Incident '{incident_id}' not found.")

    approved = payload.get("approved", False)
    if not approved:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Remediation rejected: 'approved' must be explicitly set to true."
        )
    result = incident_service.remediate_incident(incident_id, approved=True)
    return result

@app.post("/incidents/{incident_id}/rollback", tags=["Remediation"])
def rollback_incident(incident_id: str):
    inc = incident_service.get_incident(incident_id)
    if not inc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Incident '{incident_id}' not found.")

    result = incident_service.rollback_incident(incident_id)
    if result.get("status") != "success":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.get("reason", "Rollback failed."))
    return result
