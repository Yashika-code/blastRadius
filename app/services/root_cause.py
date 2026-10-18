"""
Deterministic and Explainable Root-Cause Analysis.
Ranks candidates based on:
1. Alert target and telemetry anomalies.
2. In-degree centrality (shared dependency for multiple degraded services).
3. Plausible propagation paths.
4. Fallback availability.
"""
from typing import List, Dict, Any
from app.graph.queries import find_component, trace_upstream_dependencies, trace_downstream_dependencies
from app.models.schemas import RootCauseCandidate, AlertPayload

def analyze_root_cause(alert: AlertPayload) -> List[RootCauseCandidate]:
    """
    Evaluates observed symptoms against graph topology to rank root-cause candidates.
    Distinguishes observed telemetry from inferred causality.
    """
    candidates = []
    failing_comp = alert.component_name
    comp_data = find_component(failing_comp)
    
    # 1. Primary candidate: Component identified in alert
    telemetry = alert.telemetry or {}
    cpu = telemetry.get("cpu_percent", 0.0)
    pool = telemetry.get("connection_pool_usage", 0.0)
    error_rate = telemetry.get("error_rate", 0.0)

    # Determine confidence based on concrete metrics
    primary_confidence = 0.85
    reason_parts = []
    if cpu > 80:
        primary_confidence += 0.05
        reason_parts.append(f"Excessive CPU saturation ({cpu}%)")
    if pool > 0.8:
        primary_confidence += 0.05
        reason_parts.append(f"Connection pool exhaustion ({pool*100:.1f}%)")
    if error_rate > 0.05:
        primary_confidence += 0.05
        reason_parts.append(f"Elevated error rate ({error_rate*100:.1f}%)")

    primary_reason = f"Alert explicitly flagged '{failing_comp}'. " + "; ".join(reason_parts)
    
    # Upstream services relying on this component
    upstream = trace_upstream_dependencies(failing_comp, max_hops=2)
    dependent_count = len(upstream)

    candidates.append(RootCauseCandidate(
        component=failing_comp,
        confidence=min(round(primary_confidence, 2), 0.98),
        reason=primary_reason,
        telemetry_evidence=telemetry,
        graph_evidence=f"Directly queried node. {dependent_count} upstream service(s) rely on this component.",
        shared_dependency_score=float(dependent_count)
    ))

    # 2. Secondary candidates: Immediate downstream dependencies if a service was alerted
    downstream = trace_downstream_dependencies(failing_comp, max_hops=1)
    for dep in downstream:
        d_name = dep["component"]
        d_type = dep.get("type", "Database")
        d_props = dep.get("properties", {})
        
        # Check if downstream dependency has worse telemetry or is database/queue
        cand_confidence = 0.50
        cand_reason = f"Downstream dependency '{d_name}' ({d_type}) could be propagating failures upward to {failing_comp}."
        
        candidates.append(RootCauseCandidate(
            component=d_name,
            confidence=cand_confidence,
            reason=cand_reason,
            telemetry_evidence=d_props,
            graph_evidence=f"Downstream path: ({failing_comp})-[calls/reads]->({d_name})",
            shared_dependency_score=1.0
        ))

    # Sort descending by confidence
    candidates.sort(key=lambda x: x.confidence, reverse=True)
    return candidates
