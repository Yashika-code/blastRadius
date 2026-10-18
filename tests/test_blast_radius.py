"""
Unit and Integration Tests for BlastRadius Engine.
Validates:
- Graph seeding and topology presence.
- Direct and transitive multi-hop blast radius traversal.
- Customer impact deduplication and tier grouping.
- Root cause ranking logic.
- Fallback path discovery.
- Missing / unknown component handling.
- Approval enforcement for remediation.
- Safe simulated remediation execution and verification.
- State rollback and exact restoration.
- Repeated remediation and repeated rollback safety.
- Unhealthy fallback target rejection.
- FalkorDB integration test when live engine is reachable.
"""
import pytest
from app.graph.seed import seed_database
from app.graph.queries import (
     find_component,
     trace_upstream_dependencies,
     get_impacted_customers,
     find_fallback_paths
)
from app.graph.client import falkor_client
from app.services.blast_radius import calculate_blast_radius
from app.services.root_cause import analyze_root_cause
from app.services.remediation import generate_remediation_plan, execute_remediation_plan
from app.adapters.infrastructure_simulator import infra_simulator
from app.models.schemas import AlertPayload

@pytest.fixture(autouse=True)
def setup_graph():
    # Seed fresh topology before each test
    seed_database(reset=True)

def test_graph_seeding_and_nodes():
    comp = find_component("user-creds-postgres")
    assert comp is not None
    assert comp["name"] == "user-creds-postgres"
    assert comp.get("node_label") == "Database" or comp.get("type") == "PostgreSQL"

    auth = find_component("auth-service")
    assert auth is not None
    assert auth["criticality"] == "tier-1"

def test_relationship_schema_consistency_and_idempotence():
    """Verify supported relationship types and that repeated seeding is idempotent."""
    mem = falkor_client.memory_graph
    expected_rel_types = {
        "CALLS", "READS_FROM", "WRITES_TO", "PUBLISHES_TO",
        "CONSUMES_FROM", "ROUTED_THROUGH", "ROUTES_TO", "FALLBACK_TO"
    }
    found_rel_types = {e["relation"] for e in mem.edges}
    # Check all found relationship types belong to our documented schema
    for r in found_rel_types:
        assert r in expected_rel_types, f"Unexpected relationship type found: {r}"

    edge_count_before = len(mem.edges)
    node_count_before = len(mem.nodes)

    # Re-seed without reset (must not create duplicates)
    seed_database(reset=False)
    assert len(mem.edges) == edge_count_before
    assert len(mem.nodes) == node_count_before

def test_blast_radius_multi_hop_traversal():
    # Failing component: user-creds-postgres
    # Direct callers: auth-service, user-profile-service
    # Transitive callers: order-service, payment-service, api-gateway
    blast = calculate_blast_radius("user-creds-postgres", max_hops=3)
    
    assert blast.root_component == "user-creds-postgres"
    assert "auth-service" in blast.directly_impacted_services
    assert "user-profile-service" in blast.directly_impacted_services
    assert len(blast.transitively_impacted_services) > 0
    assert "order-service" in blast.transitively_impacted_services

def test_customer_impact_deduplication_and_tiers():
    customers = get_impacted_customers("user-creds-postgres")
    assert len(customers) > 0
    
    # Check deduplication
    ids = [c.id for c in customers]
    assert len(ids) == len(set(ids)), "Customer IDs must not contain duplicates"

    # Tier-1 check
    tier_1_custs = [c for c in customers if c.tier == "Tier-1"]
    assert len(tier_1_custs) >= 2, "Should impact mission-critical Tier-1 customers"

def test_missing_or_unknown_component():
    blast = calculate_blast_radius("non-existent-service-xyz")
    assert blast.directly_impacted_services == []
    assert blast.impacted_customers == []

def test_root_cause_candidate_ranking():
    alert = AlertPayload(
        alert_id="test-alert-1",
        component_name="user-creds-postgres",
        alert_type="DatabaseSaturation",
        severity="critical",
        telemetry={"cpu_percent": 95.0, "connection_pool_usage": 0.95}
    )
    candidates = analyze_root_cause(alert)
    assert len(candidates) > 0
    assert candidates[0].component == "user-creds-postgres"
    assert candidates[0].confidence > 0.85
    assert "saturation" in candidates[0].reason.lower() or "connection" in candidates[0].reason.lower()

def test_fallback_paths_discovery():
    fallbacks = find_fallback_paths("user-creds-postgres")
    assert len(fallbacks) >= 2
    targets = [f.to_service for f in fallbacks]
    assert "auth-redis-cache" in targets or "user-profile-replica" in targets

def test_remediation_approval_enforcement():
    blast = calculate_blast_radius("user-creds-postgres", max_hops=3)
    plan = generate_remediation_plan("inc-test-approval", "user-creds-postgres", blast, mode="approval")
    
    # Attempt execution without approval
    res = execute_remediation_plan(plan, approved_by_user=False)
    assert res["status"] == "rejected"
    assert "approval" in res["reason"].lower()

def test_simulated_remediation_execution_and_rollback():
    blast = calculate_blast_radius("user-creds-postgres", max_hops=3)
    plan = generate_remediation_plan("inc-test-exec", "user-creds-postgres", blast, mode="approval")
    
    # Execute with explicit approval
    res = execute_remediation_plan(plan, approved_by_user=True)
    assert res["status"] == "completed"
    assert res["actions_executed"] > 0

    # Verify replica changed to read_only=False
    replica = find_component("user-profile-replica")
    assert replica["read_only"] is False

    # Test rollback
    rb_res = infra_simulator.rollback("inc-test-exec")
    assert rb_res["status"] == "success"

    # Verify state restored
    replica_restored = find_component("user-profile-replica")
    assert replica_restored["read_only"] is True

def test_repeated_remediation_and_rollback_safety():
    """Ensure that repeated execution and rollbacks do not corrupt state."""
    blast = calculate_blast_radius("user-creds-postgres", max_hops=3)
    plan = generate_remediation_plan("inc-repeated-test", "user-creds-postgres", blast, mode="approval")
    
    res1 = execute_remediation_plan(plan, approved_by_user=True)
    assert res1["status"] == "completed"

    rb1 = infra_simulator.rollback("inc-repeated-test")
    assert rb1["status"] == "success"

    # Repeated rollback should succeed from preserved snapshot or report clearly
    rb2 = infra_simulator.rollback("inc-repeated-test")
    assert rb2["status"] == "success"

def test_unhealthy_fallback_target_rejection():
    """Ensure simulator rejects routing to unhealthy fallback target."""
    mem = falkor_client.memory_graph
    # Temporarily degrade user-profile-replica
    mem.nodes["user-profile-replica"]["properties"]["status"] = "degraded"
    
    action = {
        "action_id": "test-act-replica-unhealthy",
        "action_type": "switch_replica",
        "target_component": "user-creds-postgres"
    }
    res = infra_simulator.execute_action(action)
    assert res["success"] is False
    assert "not healthy" in res["error"].lower()

@pytest.mark.skipif(not falkor_client.is_connected, reason="Live FalkorDB server not reachable on localhost:6379 (requires Docker FalkorDB container)")
def test_live_falkordb_connectivity_and_cypher():
    """
    Real FalkorDB Integration Test:
    Executes a real Cypher write, read verification, and teardown cleanup against live FalkorDB.
    """
    # 1. Ping
    ping_res = falkor_client.query("RETURN 1 AS ping")
    assert ping_res is not None

    # 2. Write isolated test entity
    test_node_id = "test-falkor-integration-node"
    falkor_client.query("MERGE (t:IntegrationTestNode {id: $id, active: true})", {"id": test_node_id})

    # 3. Read back from real FalkorDB
    read_res = falkor_client.query("MATCH (t:IntegrationTestNode {id: $id}) RETURN t.id, t.active", {"id": test_node_id})
    assert len(read_res.result_set) >= 1
    assert read_res.result_set[0][0] == test_node_id

    # 4. Teardown / Cleanup
    falkor_client.query("MATCH (t:IntegrationTestNode {id: $id}) DETACH DELETE t", {"id": test_node_id})
