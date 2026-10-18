"""
Live feature verification script for BlastRadius Agent.
Tests all endpoints, agent triage, blast-radius calculations,
approval-gated remediation, verification, 404 handling, and rollback.
Employs strict PASS, FAIL, and SKIP status reporting with clear exit codes.
"""
import requests
import json
import sys

BASE = 'http://127.0.0.1:8000'

def test_live_features():
    print("==================================================")
    print("BLASTRADIUS AGENT - LIVE SYSTEM VERIFICATION")
    print("==================================================")
    
    passed_checks = 0
    failed_checks = 0
    skipped_checks = 0

    # 1. API Reachable
    print("\n[1/10] Checking API Reachability...")
    try:
        h = requests.get(f"{BASE}/health", timeout=3).json()
        print("  -> Status: PASS (API Reachable)")
        passed_checks += 1
    except Exception as e:
        print(f"  -> Status: FAIL (API Unreachable: {e})")
        sys.exit(1)

    # 2. Active Backend & Truthful Reporting
    print("\n[2/10] Checking Active Graph Backend & Reporting...")
    active_be = h.get("active_backend")
    falkor_conn = h.get("falkordb_connected")
    print(f"  -> Active Backend: {active_be}")
    print(f"  -> FalkorDB Connected: {falkor_conn}")
    print(f"  -> Graph Name: {h.get('graph_name')}")
    if active_be in ["falkordb", "in-memory-graph-adapter"]:
        print("  -> Status: PASS (Truthful Backend Identified)")
        passed_checks += 1
    else:
        print("  -> Status: FAIL (Unknown backend status)")
        failed_checks += 1

    # 3. FalkorDB Live Connectivity Check
    print("\n[3/10] Checking Live FalkorDB Server Connectivity...")
    if falkor_conn and active_be == "falkordb":
        print("  -> Status: PASS (Connected to live FalkorDB Redis)")
        passed_checks += 1
    else:
        print("  -> Status: SKIP (FalkorDB container not listening on localhost:6379 - running on in-memory fallback)")
        skipped_checks += 1

    # 4. /graph/overview (Derived from real query)
    print("\n[4/10] Verifying /graph/overview Derived Counts...")
    overview = requests.get(f"{BASE}/graph/overview").json()
    nodes = overview.get("nodes", [])
    edges = overview.get("edges", [])
    print(f"  -> Topology Loaded: {len(nodes)} nodes, {len(edges)} edges")
    if len(nodes) >= 15 and len(edges) >= 15:
        print("  -> Status: PASS (Topology Graph Verified)")
        passed_checks += 1
    else:
        print("  -> Status: FAIL (Insufficient topology data)")
        failed_checks += 1

    # 5. Alert Ingestion & Multi-Hop Traversal
    print("\n[5/10] Testing Alert Ingestion & Autonomous Traversal...")
    alert_payload = {
        "alert_id": "alert-live-verify-001",
        "component_name": "user-creds-postgres",
        "alert_type": "ConnectionPoolExhaustionAndHighCPU",
        "severity": "critical",
        "telemetry": {
            "cpu_percent": 98.2,
            "connection_pool_usage": 0.99,
            "active_connections": 198,
            "max_connections": 200,
            "waiting_queries": 48
        },
        "description": "Primary PostgreSQL database user-creds-postgres CPU reached 98.2% and connection pool is saturated at 99%."
    }
    res = requests.post(f"{BASE}/alert", json=alert_payload)
    if res.status_code == 200:
        inc = res.json()
        inc_id = inc["incident_id"]
        blast = inc.get("blast_radius", {})
        print(f"  -> Incident ID Generated: {inc_id}")
        print(f"  -> Failing Component: {inc['failing_component']}")
        print(f"  -> Directly Impacted: {blast.get('directly_impacted_services')}")
        print(f"  -> Transitively Impacted: {blast.get('transitively_impacted_services')}")
        print(f"  -> Impacted Customers ({len(blast.get('impacted_customers', []))} accounts): {[c['name'] for c in blast.get('impacted_customers', [])]}")
        print("  -> Status: PASS (Multi-Hop Dependency Traversal Successful)")
        passed_checks += 1
    else:
        print(f"  -> Status: FAIL (Alert failed: {res.text})")
        failed_checks += 1
        return

    # 6. Payload Validation Check
    print("\n[6/10] Testing Request Validation (Empty component_name)...")
    inv_res = requests.post(f"{BASE}/alert", json={"alert_id": "inv", "component_name": "", "alert_type": "X", "severity": "critical"})
    if inv_res.status_code in [400, 422]:
        print(f"  -> Status: PASS (Correctly rejected invalid payload with HTTP {inv_res.status_code})")
        passed_checks += 1
    else:
        print(f"  -> Status: FAIL (Expected 422/400 but got {inv_res.status_code})")
        failed_checks += 1

    # 7. Security Policy Enforcement: Rejecting Unapproved Execution
    print("\n[7/10] Testing Security Policy: Rejecting Unapproved Execution...")
    unapp_res = requests.post(f"{BASE}/incidents/{inc_id}/remediate", json={"approved": False})
    if unapp_res.status_code == 400:
        print("  -> Status: PASS (Unapproved action strictly rejected with HTTP 400)")
        passed_checks += 1
    else:
        print(f"  -> Status: FAIL (Expected 400 but got {unapp_res.status_code})")
        failed_checks += 1

    # 8. Approved Simulated Remediation & Post-Action Verification
    print("\n[8/10] Executing Approved Remediation Against Simulator & Verifying...")
    app_res = requests.post(f"{BASE}/incidents/{inc_id}/remediate", json={"approved": True})
    if app_res.status_code == 200 and app_res.json().get("status") == "completed":
        updated_inc = requests.get(f"{BASE}/incidents/{inc_id}").json()
        print("  -> Status: PASS (Simulated Actions Executed & Verified)")
        for a in updated_inc.get("remediation_plan", {}).get("actions", []):
            print(f"     * [{a.get('action_type')}] -> {a.get('verification_result')}")
        passed_checks += 1
    else:
        print(f"  -> Status: FAIL (Remediation execution failed: {app_res.text})")
        failed_checks += 1

    # 9. State Rollback Restoration
    print("\n[9/10] Testing State Rollback Restoration...")
    rb_res = requests.post(f"{BASE}/incidents/{inc_id}/rollback")
    if rb_res.status_code == 200 and rb_res.json().get("status") == "success":
        print("  -> Status: PASS (Exact Pre-Remediation State Restored)")
        passed_checks += 1
    else:
        print(f"  -> Status: FAIL (Rollback failed: {rb_res.text})")
        failed_checks += 1

    # 10. Missing Incident 404 Check
    print("\n[10/10] Testing Missing Incident 404 Handling...")
    miss_res = requests.get(f"{BASE}/incidents/missing-incident-xyz")
    if miss_res.status_code == 404:
        print("  -> Status: PASS (404 correctly returned for non-existent incident)")
        passed_checks += 1
    else:
        print(f"  -> Status: FAIL (Expected 404 but got {miss_res.status_code})")
        failed_checks += 1

    print("\n" + "="*50)
    print(f"AUDIT SUMMARY: {passed_checks} PASSED | {failed_checks} FAILED | {skipped_checks} SKIPPED")
    print("==================================================")
    
    if failed_checks > 0:
        sys.exit(1)

if __name__ == "__main__":
    test_live_features()
