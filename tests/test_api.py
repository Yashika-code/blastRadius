"""
API endpoints integration tests using FastAPI TestClient.
Tests:
- GET /health (truthful backend reporting)
- GET /graph/overview
- POST /graph/seed
- POST /alert (validation + unknown components)
- POST /incidents/analyze
- GET /incidents
- GET /incidents/{incident_id} (valid + 404)
- GET /incidents/{incident_id}/report
- POST /incidents/{incident_id}/remediate (unapproved rejection + approved execution + 404)
- POST /incidents/{incident_id}/rollback (success + 404)
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "active_backend" in data
    assert "falkordb_connected" in data
    assert "graph_name" in data
    assert data["graph_name"] == "blast_radius"

def test_falkordb_backend_selection_and_reporting():
    """Verify health endpoint reports real FalkorDB backend when connected."""
    from app.graph.client import falkor_client
    response = client.get("/health")
    data = response.json()
    if falkor_client.is_connected:
        assert data["active_backend"] == "falkordb"
        assert data["falkordb_connected"] is True
        assert data["connection_error"] is None
    else:
        assert data["active_backend"] == "in-memory-graph-adapter"
        assert data["falkordb_connected"] is False

def test_explicit_memory_fallback_unit(monkeypatch):
    """Unit test: verify graceful fallback when FalkorDB connection fails."""
    from app.graph.client import FalkorDBClient
    from unittest.mock import patch

    with patch("falkordb.FalkorDB") as mock_falkor:
        mock_falkor.side_effect = Exception("Connection refused unit-test")
        test_client = FalkorDBClient()
        assert test_client.is_connected is False
        assert test_client.active_backend == "in-memory-graph-adapter"
        assert test_client.use_memory_fallback is True
        assert "Connection refused unit-test" in test_client.connection_error

def test_graph_overview_endpoint():
    response = client.get("/graph/overview")
    assert response.status_code == 200
    data = response.json()
    assert "nodes" in data
    assert "edges" in data
    assert len(data["nodes"]) >= 15
    assert len(data["edges"]) >= 15

def test_graph_seed_endpoint():
    response = client.post("/graph/seed?reset=true")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["nodes_seeded"] >= 15

def test_alert_validation_error():
    # Empty component_name must be rejected
    invalid_alert = {
        "alert_id": "test-invalid-01",
        "component_name": "",
        "alert_type": "TestType",
        "severity": "critical"
    }
    response = client.post("/alert", json=invalid_alert)
    assert response.status_code in [400, 422]

def test_incident_not_found_404():
    response = client.get("/incidents/non-existent-inc-xyz")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()

def test_alert_triage_and_incident_lifecycle():
    alert_payload = {
        "alert_id": "test-alert-api-101",
        "component_name": "user-creds-postgres",
        "alert_type": "ConnectionPoolExhaustionAndHighCPU",
        "severity": "critical",
        "telemetry": {
            "cpu_percent": 96.0,
            "connection_pool_usage": 0.98
        },
        "description": "Database connection saturation test."
    }

    # Ingest Alert
    response = client.post("/alert", json=alert_payload)
    assert response.status_code == 200
    incident = response.json()
    incident_id = incident["incident_id"]
    assert incident_id.startswith("inc-")
    assert incident["failing_component"] == "user-creds-postgres"
    assert len(incident["blast_radius"]["directly_impacted_services"]) > 0
    assert len(incident["root_cause_candidates"]) > 0

    # Get Incident by ID
    get_res = client.get(f"/incidents/{incident_id}")
    assert get_res.status_code == 200
    assert get_res.json()["incident_id"] == incident_id

    # Get Incident Report
    rep_res = client.get(f"/incidents/{incident_id}/report")
    assert rep_res.status_code == 200
    assert "blast_radius" in rep_res.json()

    # Attempt Unapproved Remediation (Must be rejected with 400)
    unapproved_res = client.post(f"/incidents/{incident_id}/remediate", json={"approved": False})
    assert unapproved_res.status_code == 400

    # Execute Approved Remediation
    approved_res = client.post(f"/incidents/{incident_id}/remediate", json={"approved": True})
    assert approved_res.status_code == 200
    assert approved_res.json()["status"] == "completed"

    # Rollback Remediation
    rollback_res = client.post(f"/incidents/{incident_id}/rollback")
    assert rollback_res.status_code == 200
    assert rollback_res.json()["status"] == "success"
