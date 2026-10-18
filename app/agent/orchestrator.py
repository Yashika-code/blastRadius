"""
Agent Orchestrator.
Executes the autonomous loop:
Alert received → component lookup → graph traversal → blast radius calculation →
root-cause ranking → fallback discovery → remediation proposal → incident report generation.

Uses LiteLLM if available and configured; seamlessly uses high-performance deterministic
graph analysis engine if LLM API keys are not supplied.
"""
import uuid
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from app.config import settings
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.tools import AVAILABLE_TOOLS
from app.models.schemas import AlertPayload, IncidentReport, BlastRadiusResult
from app.services.blast_radius import calculate_blast_radius
from app.services.root_cause import analyze_root_cause
from app.services.remediation import generate_remediation_plan

logger = logging.getLogger(__name__)

class AgentOrchestrator:
    def __init__(self):
        self.model = settings.LLM_MODEL
        self.has_llm = bool(settings.OPENAI_API_KEY or settings.GEMINI_API_KEY or settings.ANTHROPIC_API_KEY)

    def run_investigation_pipeline(
        self,
        alert: AlertPayload,
        incident_id: Optional[str] = None
    ) -> IncidentReport:
        """
        Executes the end-to-end incident triage and analysis pipeline.
        Uses deterministic graph queries for ground-truth dependencies,
        and augments with LLM synthesis when configured.
        """
        inc_id = incident_id or f"inc-{uuid.uuid4().hex[:8]}"
        created_at = datetime.now(timezone.utc).isoformat()
        
        # Step 1: Component verification & blast radius
        comp_info = AVAILABLE_TOOLS["inspect_component"](alert.component_name)
        blast_radius = calculate_blast_radius(
            alert.component_name,
            max_hops=settings.MAX_TRAVERSAL_HOPS,
            incident_timestamp=alert.timestamp
        )
        
        # Step 2: Root cause analysis
        root_causes = analyze_root_cause(alert)
        
        # Step 3: Safe remediation planning
        remediation_plan = generate_remediation_plan(
            incident_id=inc_id,
            failing_component=alert.component_name,
            blast_radius=blast_radius,
            mode=settings.DEFAULT_REMEDIATION_MODE
        )

        # Step 4: LLM synthesis (if LLM provider configured)
        llm_summary = self._synthesize_with_llm(alert, blast_radius, root_causes, remediation_plan)

        # Step 5: Construct complete structured report
        report = IncidentReport(
            incident_id=inc_id,
            created_at=created_at,
            alert=alert,
            failing_component=alert.component_name,
            observed_evidence={
                "telemetry": alert.telemetry,
                "component_status": comp_info.get("component", {}).get("status", "unknown"),
                "llm_synthesis": llm_summary
            },
            root_cause_candidates=root_causes,
            blast_radius=blast_radius,
            remediation_plan=remediation_plan,
            audit_history=[{
                "timestamp": created_at,
                "event": "INCIDENT_TRIAGED",
                "details": f"Analyzed failing component {alert.component_name} across {blast_radius.max_hops} graph hops."
            }],
            status="investigating",
            remaining_risks=[
                f"SLA breach risk for {len(blast_radius.impacted_customers)} customer(s) if connection saturation continues.",
                f"{len(blast_radius.critical_services_affected)} critical Tier-1 service(s) impacted in path."
            ],
            follow_up_checks=[
                "Monitor database connection pool threads and transaction duration.",
                "Verify replica replication lag remains under 1000ms.",
                "Confirm fallback cache hit ratio reaches > 90%."
            ]
        )
        return report

    def _synthesize_with_llm(
        self,
        alert: AlertPayload,
        blast: BlastRadiusResult,
        root_causes: list,
        plan: Any
    ) -> str:
        """Invokes LiteLLM if API keys are set, otherwise returns deterministic summary."""
        if not self.has_llm:
            return (
                f"[Deterministic Graph Analysis Engine] Incident {alert.alert_id} triage complete. "
                f"Failing component '{alert.component_name}' directly impacts {len(blast.directly_impacted_services)} service(s) "
                f"and transitively impacts {len(blast.transitively_impacted_services)} service(s). "
                f"{len(blast.impacted_customers)} customer account(s) affected across {list(blast.impacted_customer_tiers.keys())}."
            )

        try:
            from litellm import completion
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"""
Please synthesize this incident based on graph evidence:
Alert: {alert.json()}
Blast Radius: Directly impacted: {blast.directly_impacted_services}, Transitively: {blast.transitively_impacted_services}
Customers affected: {[c.name + ' (' + c.tier + ')' for c in blast.impacted_customers]}
Primary Root Cause: {root_causes[0].json() if root_causes else 'None'}
Proposed Remediation: {[a.action_type for a in plan.actions]}

Provide a 3-sentence executive summary for the on-call engineer distinguishing facts vs proposals.
"""}
            ]
            response = completion(model=self.model, messages=messages, temperature=0.1)
            return response.choices[0].message.content
        except Exception as e:
            logger.warning(f"LLM synthesis fallback: {e}")
            return (
                f"[Deterministic Analysis Engine] Saturated component '{alert.component_name}' poses immediate cascading "
                f"failure risk to Tier-1 services {blast.critical_services_affected}."
            )

orchestrator = AgentOrchestrator()
