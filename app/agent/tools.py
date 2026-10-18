"""
Agent tool definitions with structured Pydantic inputs and bounded outputs.
Exposes graph inspection, blast radius calculation, customer impact,
root cause ranking, remediation planning, execution, and verification.
"""
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from app.graph.queries import (
    find_component,
    trace_upstream_dependencies,
    trace_downstream_dependencies,
    find_fallback_paths,
    get_impacted_customers
)
from app.services.blast_radius import calculate_blast_radius
from app.services.root_cause import analyze_root_cause
from app.services.remediation import generate_remediation_plan, execute_remediation_plan
from app.models.schemas import AlertPayload, RemediationPlan

class InspectComponentInput(BaseModel):
    name: str = Field(description="Name or ID of the component to inspect")

def tool_inspect_component(name: str) -> Dict[str, Any]:
    comp = find_component(name)
    if not comp:
        return {"found": False, "error": f"Component '{name}' not found in graph topology."}
    return {"found": True, "component": comp}

class TraceBlastRadiusInput(BaseModel):
    name: str = Field(description="Failing component name")
    max_hops: int = Field(default=3, description="Maximum traversal depth (1 to 5)")

def tool_trace_blast_radius(name: str, max_hops: int = 3) -> Dict[str, Any]:
    bounded_hops = max(1, min(max_hops, 5))
    res = calculate_blast_radius(name, max_hops=bounded_hops)
    return res.dict()

class AnalyzeCustomerImpactInput(BaseModel):
    name: str = Field(description="Failing component name")

def tool_analyze_customer_impact(name: str) -> Dict[str, Any]:
    customers = get_impacted_customers(name)
    tiers: Dict[str, int] = {}
    for c in customers:
        tiers[c.tier] = tiers.get(c.tier, 0) + 1
    return {
        "impacted_customer_count": len(customers),
        "tiers": tiers,
        "customers": [c.dict() for c in customers]
    }

class FindRootCausesInput(BaseModel):
    alert_payload: Dict[str, Any] = Field(description="Incoming alert payload")

def tool_find_root_causes(alert_payload: Dict[str, Any]) -> Dict[str, Any]:
    alert = AlertPayload(**alert_payload)
    candidates = analyze_root_cause(alert)
    return {"candidates": [c.dict() for c in candidates]}

class ProposeRemediationInput(BaseModel):
    incident_id: str
    failing_component: str
    mode: str = "approval"

def tool_propose_remediation(incident_id: str, failing_component: str, mode: str = "approval") -> Dict[str, Any]:
    blast = calculate_blast_radius(failing_component, max_hops=3)
    plan = generate_remediation_plan(incident_id, failing_component, blast, mode=mode)
    return plan.dict()

class ExecuteRemediationInput(BaseModel):
    plan_dict: Dict[str, Any]
    approved: bool = Field(default=False, description="Explicit approval confirmation")

def tool_execute_remediation(plan_dict: Dict[str, Any], approved: bool = False) -> Dict[str, Any]:
    plan = RemediationPlan(**plan_dict)
    return execute_remediation_plan(plan, approved_by_user=approved)

# Tool Registry Map for Agent Orchestrator
AVAILABLE_TOOLS = {
    "inspect_component": tool_inspect_component,
    "trace_blast_radius": tool_trace_blast_radius,
    "analyze_customer_impact": tool_analyze_customer_impact,
    "find_root_causes": tool_find_root_causes,
    "propose_remediation": tool_propose_remediation,
    "execute_remediation": tool_execute_remediation
}
