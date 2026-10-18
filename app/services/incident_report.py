"""
Incident Management, Storage, and Lifecycle Tracking Service.
"""
from typing import Dict, Optional, List, Any
from datetime import datetime, timezone
from app.models.schemas import IncidentReport, AlertPayload
from app.agent.orchestrator import orchestrator
from app.services.remediation import execute_remediation_plan
from app.adapters.infrastructure_simulator import infra_simulator

class IncidentService:
    def __init__(self):
        self.incidents: Dict[str, IncidentReport] = {}

    def create_and_analyze(self, alert: AlertPayload) -> IncidentReport:
        report = orchestrator.run_investigation_pipeline(alert)
        self.incidents[report.incident_id] = report
        return report

    def get_incident(self, incident_id: str) -> Optional[IncidentReport]:
        return self.incidents.get(incident_id)

    def list_incidents(self) -> List[IncidentReport]:
        return list(self.incidents.values())

    def remediate_incident(self, incident_id: str, approved: bool) -> Dict[str, Any]:
        incident = self.incidents.get(incident_id)
        if not incident:
            return {"status": "error", "message": f"Incident {incident_id} not found."}
        
        if not incident.remediation_plan:
            return {"status": "error", "message": "No remediation plan formulated for this incident."}

        res = execute_remediation_plan(incident.remediation_plan, approved_by_user=approved)
        
        # Update audit history
        incident.audit_history.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": "REMEDIATION_EXECUTED" if res.get("status") == "completed" else "REMEDIATION_REJECTED",
            "details": res
        })

        if res.get("status") == "completed":
            incident.status = "mitigated"
            incident.verification_summary = "Simulated remediation completed and verified against graph state."
        
        return res

    def rollback_incident(self, incident_id: str) -> Dict[str, Any]:
        incident = self.incidents.get(incident_id)
        if not incident:
            return {"status": "error", "message": f"Incident {incident_id} not found."}
        
        res = infra_simulator.rollback(incident_id)
        if res.get("status") == "success":
            incident.status = "rolled_back"
            if incident.remediation_plan:
                incident.remediation_plan.status = "rolled_back"
            incident.audit_history.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event": "ROLLBACK_EXECUTED",
                "details": res
            })
        return res

incident_service = IncidentService()
