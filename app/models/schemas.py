"""
Pydantic data models for BlastRadius Agent.
"""
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from enum import Enum

class NodeCriticality(str, Enum):
    TIER_1 = "tier-1"
    TIER_2 = "tier-2"
    TIER_3 = "tier-3"

class ComponentStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    ISOLATED = "isolated"
    OFFLINE = "offline"

class CustomerTier(str, Enum):
    TIER_1 = "Tier-1"
    TIER_2 = "Tier-2"
    TIER_3 = "Tier-3"

# Node schemas
class ServiceNode(BaseModel):
    name: str
    status: ComponentStatus = ComponentStatus.HEALTHY
    owner_team: str = "infrastructure"
    criticality: NodeCriticality = NodeCriticality.TIER_2
    latency_ms: float = 15.0
    error_rate: float = 0.01
    health_score: float = 0.99

class DatabaseNode(BaseModel):
    name: str
    type: str = "PostgreSQL"
    status: ComponentStatus = ComponentStatus.HEALTHY
    read_only: bool = False
    cpu_percent: float = 25.0
    connection_pool_usage: float = 0.35

class QueueNode(BaseModel):
    name: str
    status: ComponentStatus = ComponentStatus.HEALTHY
    backlog: int = 0
    consumer_lag: int = 0

class CustomerNode(BaseModel):
    id: str
    name: str
    tier: CustomerTier = CustomerTier.TIER_2
    sla_minutes: int = 60
    business_criticality: str = "medium"

class IngressNode(BaseModel):
    name: str
    status: ComponentStatus = ComponentStatus.HEALTHY
    region: str = "us-east-1"

# Alert schemas
class AlertPayload(BaseModel):
    alert_id: str
    component_name: str
    alert_type: str
    severity: str  # critical, warning, info
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    telemetry: Dict[str, Any] = Field(default_factory=dict)
    description: Optional[str] = None

# Analysis schemas
class GraphPathSegment(BaseModel):
    source: str
    relationship: str
    target: str
    properties: Dict[str, Any] = Field(default_factory=dict)

class ImpactedCustomer(BaseModel):
    id: str
    name: str
    tier: str
    sla_minutes: int
    business_criticality: str
    path_summary: str

class BlastRadiusResult(BaseModel):
    root_component: str
    directly_impacted_services: List[str] = Field(default_factory=list)
    transitively_impacted_services: List[str] = Field(default_factory=list)
    impacted_infrastructure: List[str] = Field(default_factory=list)
    impacted_customers: List[ImpactedCustomer] = Field(default_factory=list)
    impacted_customer_tiers: Dict[str, int] = Field(default_factory=dict)
    paths: List[List[str]] = Field(default_factory=list)
    max_hops: int = 3
    critical_services_affected: List[str] = Field(default_factory=list)
    sla_exposure_minutes: int = 0
    sla_status: str = "potential_exposure"  # "potential_exposure", "breached", "not_evaluated", "unknown"
    elapsed_time_minutes: Optional[int] = None

class RootCauseCandidate(BaseModel):
    component: str
    confidence: float  # 0.0 to 1.0
    reason: str
    telemetry_evidence: Dict[str, Any] = Field(default_factory=dict)
    graph_evidence: str
    shared_dependency_score: float = 0.0

class FallbackPath(BaseModel):
    from_service: str
    to_service: str
    protocol: str = "http"
    circuit_broken: bool = False
    status: str = "available"

# Remediation schemas
class RemediationAction(BaseModel):
    action_id: str
    target_component: str
    relationship: Optional[str] = None
    action_type: str  # e.g., trip_circuit_breaker, switch_replica, isolate_component, enable_fallback_cache, adjust_traffic_weight
    reason: str
    expected_impact: str
    preconditions: List[str] = Field(default_factory=list)
    risk_level: str = "medium"  # low, medium, high
    reversibility: bool = True
    approved: bool = False
    simulated: bool = True
    execution_result: Optional[str] = None
    verification_result: Optional[str] = None
    executed_at: Optional[str] = None

class RemediationPlan(BaseModel):
    incident_id: str
    mode: str = "approval"  # observe, approval, simulation
    actions: List[RemediationAction] = Field(default_factory=list)
    requires_approval: bool = True
    status: str = "pending"  # pending, approved, executing, completed, failed, rolled_back

class IncidentReport(BaseModel):
    incident_id: str
    created_at: str
    alert: AlertPayload
    failing_component: str
    observed_evidence: Dict[str, Any]
    root_cause_candidates: List[RootCauseCandidate]
    blast_radius: BlastRadiusResult
    remediation_plan: Optional[RemediationPlan] = None
    audit_history: List[Dict[str, Any]] = Field(default_factory=list)
    verification_summary: Optional[str] = None
    status: str = "investigating"  # investigating, remediating, mitigated, resolved
    remaining_risks: List[str] = Field(default_factory=list)
    follow_up_checks: List[str] = Field(default_factory=list)
