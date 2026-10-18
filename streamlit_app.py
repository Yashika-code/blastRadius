"""
Standalone Streamlit Entrypoint for BlastRadius Agent.
Designed for Streamlit Community Cloud and one-click cloud deployment.
Automatically runs in embedded mode (direct python services + in-memory graph)
if external FastAPI backend is not running, and seamlessly connects to FastAPI
when available!
"""
import os
import sys
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List

import streamlit as st
import pandas as pd
import requests

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Import internal application modules for self-contained / cloud deployment
from app.graph.client import falkor_client
from app.graph.seed import seed_database
from app.graph.queries import get_graph_overview, find_component
from app.services.incident_report import incident_service
from app.models.schemas import AlertPayload
from app.adapters.infrastructure_simulator import infra_simulator

# Configure page
st.set_page_config(
    page_title="BlastRadius Agent — SRE Command Center",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for Dark Charcoal & Slate SRE Command Center aesthetics
st.markdown("""
<style>
    .stApp {
        background-color: #0d1117;
        color: #c9d1d9;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    div[data-testid="stMetric"] {
        background-color: #161b22;
        border: 1px solid #30363d;
        border-radius: 8px;
        padding: 14px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
    }
    div[data-testid="stMetricValue"] {
        color: #58a6ff;
        font-weight: 700;
        font-size: 1.8rem !important;
    }
    div[data-testid="stMetricLabel"] {
        color: #8b949e;
        font-size: 0.85rem !important;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .command-box {
        background-color: #161b22;
        border: 1px solid #30363d;
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 16px;
    }
    .badge-critical {
        background-color: #f85149;
        color: #ffffff;
        padding: 3px 8px;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: 600;
    }
    .badge-warning {
        background-color: #d29922;
        color: #0d1117;
        padding: 3px 8px;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: 600;
    }
    .badge-healthy {
        background-color: #238636;
        color: #ffffff;
        padding: 3px 8px;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: 600;
    }
    .badge-simulated {
        background-color: #1f6feb;
        color: #ffffff;
        padding: 2px 6px;
        border-radius: 3px;
        font-size: 0.75rem;
    }
</style>
""", unsafe_allow_html=True)

# Determine API connection or embedded service fallback
API_BASE = os.environ.get("API_BASE", "http://127.0.0.1:8000")

def is_api_online() -> bool:
    try:
        r = requests.get(f"{API_BASE}/health", timeout=1)
        return r.status_code == 200
    except Exception:
        return False

API_ONLINE = is_api_online()

# Initialize graph topology on first load
if "initialized" not in st.session_state:
    if not API_ONLINE:
        seed_database(reset=False)
    st.session_state["initialized"] = True

# Helper functions that work either via REST or embedded services
def fetch_graph_overview() -> Dict[str, Any]:
    if API_ONLINE:
        try:
            return requests.get(f"{API_BASE}/graph/overview", timeout=2).json()
        except Exception:
            pass
    return get_graph_overview()

def fetch_incidents() -> List[Dict[str, Any]]:
    if API_ONLINE:
        try:
            return requests.get(f"{API_BASE}/incidents", timeout=2).json()
        except Exception:
            pass
    raw_list = incident_service.list_incidents()
    return [i.model_dump() if hasattr(i, "model_dump") else i for i in raw_list]

def execute_reseed() -> bool:
    if API_ONLINE:
        try:
            r = requests.post(f"{API_BASE}/graph/seed?reset=true", timeout=3)
            return r.status_code == 200
        except Exception:
            pass
    seed_database(reset=True)
    return True

def ingest_alert(alert_payload: Dict[str, Any]) -> Dict[str, Any]:
    if API_ONLINE:
        try:
            r = requests.post(f"{API_BASE}/alert", json=alert_payload, timeout=5)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
    alert_obj = AlertPayload(**alert_payload)
    return incident_service.create_and_analyze(alert_obj).model_dump()

def remediate_incident(incident_id: str, approved: bool) -> Dict[str, Any]:
    if API_ONLINE:
        try:
            r = requests.post(f"{API_BASE}/incidents/{incident_id}/remediate", json={"approved": approved}, timeout=5)
            return r.json()
        except Exception as e:
            return {"error": str(e)}
    res = incident_service.remediate_incident(incident_id, approved=approved)
    return res or {"error": "Incident not found or failed"}

def rollback_incident(incident_id: str) -> Dict[str, Any]:
    if API_ONLINE:
        try:
            r = requests.post(f"{API_BASE}/incidents/{incident_id}/rollback", timeout=5)
            return r.json()
        except Exception as e:
            return {"error": str(e)}
    res = incident_service.rollback_incident(incident_id)
    return res or {"error": "Incident not found or failed"}

def get_incident(incident_id: str) -> Dict[str, Any]:
    if API_ONLINE:
        try:
            r = requests.get(f"{API_BASE}/incidents/{incident_id}", timeout=2)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
    res = incident_service.get_incident(incident_id)
    return res.model_dump() if res else {}

# Sidebar: Controls & Connection Status
with st.sidebar:
    st.markdown("### ⚡ **BlastRadius Agent**")
    st.caption("Track 01: Agents That Act on Connected Data")
    st.markdown("---")
    
    if API_ONLINE:
        try:
            health_resp = requests.get(f"{API_BASE}/health", timeout=2)
            h_data = health_resp.json()
            active_be = h_data.get('active_backend', 'unknown')
            falkor_conn = h_data.get('falkordb_connected', False)
            st.success("🟢 **Backend API:** Online (FastAPI)")
            if falkor_conn and active_be == "falkordb":
                st.success("🟢 **Graph Database:** FalkorDB (Connected)")
            else:
                st.warning(f"⚠️ **Graph Engine:** In-Memory Fallback")
        except Exception:
            st.warning("⚠️ **Mode:** Embedded / Standalone")
    else:
        st.info("ℹ️ **Mode:** Embedded Standalone (Cloud-Ready)")
        status_report = falkor_client.get_status_report()
        if status_report.get("falkordb_connected"):
            st.success("🟢 **Graph Database:** FalkorDB (Connected)")
        else:
            st.info("🌐 **Graph Database:** In-Memory Graph Adapter")

    st.markdown("---")
    st.subheader("Interactive Actions")
    
    if st.button("🔄 Re-Seed Topology Graph", use_container_width=True):
        if execute_reseed():
            st.success("Graph topology refreshed!")
            st.rerun()

    st.markdown("---")
    st.subheader("One-Click Demo")
    if st.button("🚀 Run Demo Incident: DB Saturation", type="primary", use_container_width=True):
        demo_alert = {
            "alert_id": f"alert-db-sat-{datetime.now(timezone.utc).strftime('%H%M%S')}",
            "component_name": "user-creds-postgres",
            "alert_type": "ConnectionPoolExhaustionAndHighCPU",
            "severity": "critical",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "telemetry": {
                "cpu_percent": 96.4,
                "connection_pool_usage": 0.98,
                "active_connections": 196,
                "max_connections": 200,
                "waiting_queries": 48
            },
            "description": "Primary PostgreSQL database user-creds-postgres CPU reached 96.4% and connection pool is saturated at 98%."
        }
        try:
            incident_data = ingest_alert(demo_alert)
            st.session_state["current_incident"] = incident_data
            st.success("Demo incident triaged successfully!")
            st.rerun()
        except Exception as e:
            st.error(f"Error triggering alert: {e}")

st.title("⚡ BlastRadius Agent — Infrastructure Intelligence")
st.markdown("*Autonomous Infrastructure Incident Triage & Cascading Failure Remediation powered by FalkorDB graph traversal.*")

st.warning("🛡️ **Simulation Only Notice:** All remediation actions, state mutations, and telemetry are strictly simulated against a local topology adapter. No production infrastructure, cloud clusters, or real databases are modified.")

# Load Overview
topo_res = fetch_graph_overview()
nodes = topo_res.get("nodes", [])
edges = topo_res.get("edges", [])
inc_list = fetch_incidents()

# Top KPI Row
kpi1, kpi2, kpi3, kpi4 = st.columns(4)
with kpi1:
    st.metric("Total Topology Nodes", len(nodes))
with kpi2:
    st.metric("Connected Dependencies", len(edges))
with kpi3:
    st.metric("Active Incidents", len(inc_list))
with kpi4:
    curr_inc = st.session_state.get("current_incident")
    if hasattr(curr_inc, "model_dump"):
        curr_inc = curr_inc.model_dump()
        st.session_state["current_incident"] = curr_inc
    if curr_inc:
        sla_exp = curr_inc.get("blast_radius", {}).get("sla_exposure_minutes", 0)
        st.metric("Potential SLA Exposure", f"{sla_exp} mins (Demo Threshold)")
    else:
        st.metric("Potential SLA Exposure", "0 mins")

# Tabs
tab_incident, tab_topology, tab_simulator, tab_custom_alert = st.tabs([
    "🚨 Live Incident Triage",
    "🗺️ Graph Topology & Dependencies",
    "🛡️ Remediation & Rollback Simulator",
    "📤 Submit Custom Alert"
])

# ----------------- TAB 1: LIVE INCIDENT TRIAGE -----------------
with tab_incident:
    if not st.session_state.get("current_incident") and inc_list:
        st.session_state["current_incident"] = inc_list[-1]

    curr_inc = st.session_state.get("current_incident")
    if hasattr(curr_inc, "model_dump"):
        curr_inc = curr_inc.model_dump()
        st.session_state["current_incident"] = curr_inc

    if not curr_inc:
        st.info("💡 No incident active. Click **'Run Demo Incident: DB Saturation'** in the sidebar to simulate an incident triage.")
    else:
        inc_id = curr_inc.get("incident_id")
        alert = curr_inc.get("alert", {})
        blast = curr_inc.get("blast_radius", {})
        root_causes = curr_inc.get("root_cause_candidates", [])
        plan = curr_inc.get("remediation_plan", {})
        
        st.markdown(f"""
        <div class="command-box">
            <span class="badge-critical">CRITICAL INCIDENT</span> <strong>{inc_id}</strong> &nbsp;|&nbsp; 
            <strong>Failing Component:</strong> <code>{alert.get('component_name')}</code> &nbsp;|&nbsp;
            <strong>Status:</strong> <span class="badge-warning">{curr_inc.get('status', '').upper()}</span>
            <p style="margin-top: 8px; margin-bottom: 0px; color: #8b949e;">{alert.get('description', '')}</p>
        </div>
        """, unsafe_allow_html=True)

        col_left, col_right = st.columns([1, 1])

        with col_left:
            st.subheader("🔍 Suspected Root Cause Ranking")
            for idx, cand in enumerate(root_causes):
                conf_pct = int(cand.get("confidence", 0) * 100)
                st.markdown(f"""
                <div class="command-box">
                    <div style="display: flex; justify-content: space-between;">
                        <strong>#{idx+1} {cand.get('component')}</strong>
                        <span class="badge-critical">Confidence: {conf_pct}%</span>
                    </div>
                    <p style="color: #c9d1d9; margin-top: 6px; font-size: 0.9rem;">{cand.get('reason')}</p>
                    <div style="font-size: 0.8rem; color: #8b949e;">
                        <strong>Graph Evidence:</strong> {cand.get('graph_evidence')}<br/>
                        <strong>Shared Dependency In-Degree:</strong> {cand.get('shared_dependency_score')}
                    </div>
                </div>
                """, unsafe_allow_html=True)

            st.subheader("💥 Cascading Blast Radius Traversal")
            st.markdown(f"**Directly Impacted Services:** `{', '.join(blast.get('directly_impacted_services', [])) or 'None'}`")
            st.markdown(f"**Transitively Impacted Services:** `{', '.join(blast.get('transitively_impacted_services', [])) or 'None'}`")
            st.markdown(f"**Critical Tier-1 Services in Blast Radius:** `{', '.join(blast.get('critical_services_affected', [])) or 'None'}`")

            with st.expander("📍 View Graph Traversal Dependency Paths", expanded=True):
                for p in blast.get("paths", []):
                    st.code(" ➔ ".join(p) if isinstance(p, list) else str(p), language="text")

        with col_right:
            st.subheader("👥 Impacted Customers by Tier")
            custs = blast.get("impacted_customers", [])
            tier_summary = blast.get("impacted_customer_tiers", {})
            
            tier_cols = st.columns(3)
            with tier_cols[0]:
                st.metric("Tier-1 (Mission Critical)", tier_summary.get("Tier-1", 0))
            with tier_cols[1]:
                st.metric("Tier-2 (High Priority)", tier_summary.get("Tier-2", 0))
            with tier_cols[2]:
                st.metric("Tier-3 (Standard)", tier_summary.get("Tier-3", 0))

            cust_table = []
            for c in custs:
                cust_table.append({
                    "Customer": c.get("name"),
                    "Tier": c.get("tier"),
                    "SLA (Minutes)": c.get("sla_minutes"),
                    "Business Criticality": c.get("business_criticality"),
                    "Routing Path": c.get("path_summary")
                })
            if cust_table:
                st.dataframe(pd.DataFrame(cust_table), use_container_width=True)

            st.subheader("🤖 Agent Reasoning & Telemetry Evidence")
            st.info(curr_inc.get("observed_evidence", {}).get("llm_synthesis", "Deterministic graph engine active."))
            
            st.download_button(
                label="📥 Download Structured Incident Report (JSON)",
                data=json.dumps(curr_inc, indent=2),
                file_name=f"incident_report_{inc_id}.json",
                mime="application/json",
                use_container_width=True
            )

# ----------------- TAB 2: GRAPH TOPOLOGY & DEPENDENCIES -----------------
with tab_topology:
    st.subheader("🗺️ Modeled Infrastructure Topology")
    st.caption("Live nodes and directed relationships registered in the graph database.")

    col_t1, col_t2 = st.columns([1, 1])
    with col_t1:
        st.markdown("#### Topology Nodes")
        node_df = []
        for n in nodes:
            node_df.append({
                "Name / ID": n.get("id"),
                "Type": n.get("type"),
                "Status": n.get("status"),
                "Criticality": n.get("criticality", n.get("tier", "N/A")),
                "Team / Region": n.get("owner_team", n.get("region", "N/A"))
            })
        st.dataframe(pd.DataFrame(node_df), use_container_width=True, height=350)

    with col_t2:
        st.markdown("#### Directed Relationships")
        edge_df = []
        for e in edges:
            edge_df.append({
                "From": e.get("from"),
                "Relation": e.get("label"),
                "To": e.get("to"),
                "Protocol / Details": e.get("protocol", e.get("weight", "N/A"))
            })
        st.dataframe(pd.DataFrame(edge_df), use_container_width=True, height=350)

# ----------------- TAB 3: REMEDIATION & ROLLBACK SIMULATOR -----------------
with tab_simulator:
    st.subheader("🛡️ Safe Remediation Engine (Approval-Gated)")
    st.caption("Actions are validated against graph fallback paths and executed against the isolated simulator. Zero destructive operations.")

    curr_inc = st.session_state.get("current_incident")
    if hasattr(curr_inc, "model_dump"):
        curr_inc = curr_inc.model_dump()
        st.session_state["current_incident"] = curr_inc

    if not curr_inc:
        st.info("Trigger or select an incident first to view and execute remediation.")
    else:
        inc_id = curr_inc.get("incident_id")
        plan = curr_inc.get("remediation_plan", {})
        actions = plan.get("actions", [])

        st.markdown(f"**Remediation Plan for Incident:** `#{inc_id}` | Mode: `<span class='badge-simulated'>{plan.get('mode', 'approval').upper()}</span>`", unsafe_allow_html=True)
        
        for idx, act in enumerate(actions):
            st.markdown(f"""
            <div class="command-box">
                <div style="display:flex; justify-content:space-between;">
                    <strong>Action #{idx+1}: {act.get('action_type').upper()}</strong>
                    <span class="badge-warning">Risk: {act.get('risk_level').upper()}</span>
                </div>
                <div style="margin-top: 6px;">
                    <strong>Target:</strong> <code>{act.get('target_component')}</code><br/>
                    <strong>Reason:</strong> {act.get('reason')}<br/>
                    <strong>Expected Impact:</strong> {act.get('expected_impact')}<br/>
                    <strong>Preconditions:</strong> {', '.join(act.get('preconditions', []))}
                </div>
                {f"<div style='margin-top:8px; color:#58a6ff;'><strong>Verification Result:</strong> {act.get('verification_result')}</div>" if act.get('verification_result') else ""}
            </div>
            """, unsafe_allow_html=True)

        col_act1, col_act2 = st.columns(2)
        with col_act1:
            approve_checked = st.checkbox("✅ I explicitly approve executing these simulated remediation actions", key="approval_chk")
            if st.button("⚡ Execute Approved Remediation Plan", type="primary", use_container_width=True):
                if not approve_checked:
                    st.error("❌ Policy Rejection: You must check the explicit approval confirmation box before execution.")
                else:
                    try:
                        rem_res = remediate_incident(inc_id, approved=True)
                        if "error" not in rem_res:
                            st.success("Remediation successfully simulated, applied, and verified against graph state!")
                            updated_inc = get_incident(inc_id)
                            st.session_state["current_incident"] = updated_inc
                            st.rerun()
                        else:
                            st.error(f"Remediation error: {rem_res.get('error')}")
                    except Exception as e:
                        st.error(f"Execution error: {e}")

        with col_act2:
            st.markdown("&nbsp;")
            if st.button("⏪ Rollback Simulated Actions", use_container_width=True):
                try:
                    rb_res = rollback_incident(inc_id)
                    if "error" not in rb_res:
                        st.success("State successfully rolled back to pre-incident snapshot!")
                        updated_inc = get_incident(inc_id)
                        st.session_state["current_incident"] = updated_inc
                        st.rerun()
                    else:
                        st.error(f"Rollback error: {rb_res.get('error')}")
                except Exception as e:
                    st.error(f"Rollback failed: {e}")

        st.subheader("📜 Incident Audit History")
        audit_history = curr_inc.get("audit_history", [])
        if audit_history:
            formatted_history = []
            for item in audit_history:
                row = dict(item)
                for k, v in row.items():
                    if isinstance(v, (dict, list)):
                        row[k] = json.dumps(v)
                formatted_history.append(row)
            st.dataframe(pd.DataFrame(formatted_history), use_container_width=True)

# ----------------- TAB 4: SUBMIT CUSTOM ALERT -----------------
with tab_custom_alert:
    st.subheader("📤 Ingest Custom Infrastructure Alert")
    st.caption("Submit any structured infrastructure alert payload to trigger real graph traversal and blast-radius triage.")
    
    with st.form("custom_alert_form"):
        c_id = st.text_input("Alert ID", value=f"alert-custom-{datetime.now(timezone.utc).strftime('%M%S')}")
        c_comp = st.selectbox("Target Component", options=[n.get("id") for n in nodes] or ["user-creds-postgres", "auth-service", "order-service"])
        c_type = st.text_input("Alert Type", value="ServiceLatencySpike")
        c_sev = st.selectbox("Severity", options=["critical", "warning", "info"])
        c_desc = st.text_area("Description", value="Elevated error rates and connection timeout spikes observed.")
        
        submitted = st.form_submit_button("Submit Alert for Triage")
        if submitted:
            custom_payload = {
                "alert_id": c_id,
                "component_name": c_comp,
                "alert_type": c_type,
                "severity": c_sev,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "telemetry": {"latency_ms": 1250, "error_rate": 0.15},
                "description": c_desc
            }
            try:
                res_inc = ingest_alert(custom_payload)
                st.session_state["current_incident"] = res_inc
                st.success("Custom alert triaged!")
                st.rerun()
            except Exception as e:
                st.error(f"Error submitting alert: {e}")
