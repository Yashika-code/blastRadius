"""
Blast-radius calculation service with bounded traversal depths,
deduplication, customer impact aggregation, and SLA exposure estimation.
"""
from typing import Dict, Any, List, Optional
from app.graph.queries import (
    find_component,
    trace_upstream_dependencies,
    get_impacted_customers
)
from app.models.schemas import BlastRadiusResult

def calculate_blast_radius(component_name: str, max_hops: int = 3, incident_timestamp: Optional[str] = None) -> BlastRadiusResult:
    """
    Computes direct and transitive dependencies affected by a failing component.
    Distinguishes potential SLA exposure thresholds from confirmed breaches.
    """
    comp = find_component(component_name)
    if not comp:
        return BlastRadiusResult(
            root_component=component_name,
            directly_impacted_services=[],
            transitively_impacted_services=[],
            impacted_infrastructure=[],
            impacted_customers=[],
            impacted_customer_tiers={},
            paths=[],
            max_hops=max_hops,
            critical_services_affected=[],
            sla_exposure_minutes=0,
            sla_status="not_evaluated",
            elapsed_time_minutes=None
        )

    upstream = trace_upstream_dependencies(component_name, max_hops=max_hops)
    
    directly_impacted = []
    transitively_impacted = []
    impacted_infra = []
    critical_services = []
    all_paths = []

    for dep in upstream:
        c_name = dep["component"]
        c_type = dep.get("type", "Service")
        hops = dep.get("hops", 1)
        props = dep.get("properties", {})
        
        all_paths.append(dep.get("path", []))
        
        if props.get("criticality") == "tier-1":
            if c_name not in critical_services:
                critical_services.append(c_name)

        if c_type == "Service":
            if hops == 1:
                if c_name not in directly_impacted:
                    directly_impacted.append(c_name)
            else:
                if c_name not in transitively_impacted:
                    transitively_impacted.append(c_name)
        elif c_type in ["Database", "Queue", "Ingress"]:
            if c_name not in impacted_infra:
                impacted_infra.append(c_name)

    # Customers
    impacted_customers = get_impacted_customers(component_name)
    tier_counts: Dict[str, int] = {}
    min_sla = 999999
    for c in impacted_customers:
        tier_counts[c.tier] = tier_counts.get(c.tier, 0) + 1
        if c.sla_minutes < min_sla:
            min_sla = c.sla_minutes

    sla_exposure = min_sla if min_sla != 999999 else 0
    
    # Calculate elapsed time and truthful SLA status
    sla_status = "potential_exposure" if impacted_customers else "not_evaluated"
    elapsed_minutes = None
    if incident_timestamp:
        try:
            from datetime import datetime, timezone
            ts = datetime.fromisoformat(incident_timestamp.replace("Z", "+00:00"))
            elapsed_seconds = (datetime.now(timezone.utc) - ts).total_seconds()
            elapsed_minutes = max(0, int(elapsed_seconds // 60))
            if sla_exposure > 0 and elapsed_minutes >= sla_exposure:
                sla_status = "breached"
            else:
                sla_status = "potential_exposure"
        except Exception:
            sla_status = "potential_exposure"

    return BlastRadiusResult(
        root_component=component_name,
        directly_impacted_services=directly_impacted,
        transitively_impacted_services=transitively_impacted,
        impacted_infrastructure=impacted_infra,
        impacted_customers=impacted_customers,
        impacted_customer_tiers=tier_counts,
        paths=all_paths,
        max_hops=max_hops,
        critical_services_affected=critical_services,
        sla_exposure_minutes=sla_exposure,
        sla_status=sla_status,
        elapsed_time_minutes=elapsed_minutes
    )
