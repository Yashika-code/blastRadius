"""
Streamlit Dashboard for BlastRadius Agent:
Autonomous Infrastructure Incident Triage & Cascading Failure Remediation.
SRE Command Center aesthetics: Dark charcoal, slate panels, cyan graph edges,
amber warnings, red critical indicators, green healthy status.
"""
import streamlit as st
import requests
import json
import pandas as pd
from datetime import datetime, timezone

# Set page configuration
st.set_page_config(
    page_title="BlastRadius Agent — SRE Command Center",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for Dark Charcoal & Slate SRE Command Center aesthetics
st.markdown("""
<style>
    /* Dark charcoal background & clean layout */
    .stApp {
        background-color: #0d1117;
        color: #c9d1d9;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    /* Metric panel cards */
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
    /* Section containers */
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
    .badge-tier1 {
        background-color: #a371f7;
        color: #ffffff;
        padding: 2px 6px;
        border-radius: 3px;
        font-size: 0.75rem;
        font-weight: bold;
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

API_BASE = "http://127.0.0.1:8000"

# Sidebar: Controls & Connection Status
with st.sidebar:
    st.markdown("### ⚡ **BlastRadius Agent**")
    st.caption("Track 01: Agents That Act on Connected Data")
    st.markdown("---")
    
    # Check Backend Status
    try:
        health_resp = requests.get(f"{API_BASE}/health", timeout=2)
        if health_resp.status_code == 200:
            h_data = health_resp.json()
            active_be = h_data.get('active_backend', 'unknown')
            falkor_conn = h_data.get('falkordb_connected', False)
            st.success(f"🟢 **Backend API:** Online")
            if falkor_conn and active_be == "falkordb":
                st.success("🟢 **Graph Database:** FalkorDB (Connected)")
            else:
                st.warning(f"⚠️ **Graph Engine:** In-Memory Fallback ({h_data.get('graph_name', 'blast_radius')})")
                st.caption("FalkorDB offline at localhost:6379. Using local in-memory graph adapter.")
        else:
            st.error("🔴 **Backend API:** Error")
    except Exception:
        st.warning("⚠️ Backend API offline (Run `python -m uvicorn app.main:app`)")

    st.markdown("---")
    st.subheader("Interactive Actions")
    
    # Re-seed button
    if st.button("🔄 Re-Seed Topology Graph", use_container_width=True):
        try:
            r = requests.post(f"{API_BASE}/graph/seed?reset=true")
            st.success("Graph topology refreshed!")
            st.rerun()
        except Exception as e:
            st.error(f"Failed to seed: {e}")

    # One-click demo incident button
    st.markdown("---")
    st.subheader("One-Click Demo")
    if st.button("🚀 Run Demo Incident: DB Saturation", type="primary", use_container_width=True):
        demo_alert = {
            "alert_id": f"alert-db-sat-{datetime.utcnow().strftime('%H%M%S')}",
            "component_name": "user-creds-postgres",
            "alert_type": "ConnectionPoolExhaustionAndHighCPU",
            "severity": "critical",
            "timestamp": datetime.utcnow().isoformat(),
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
            res = requests.post(f"{API_BASE}/alert", json=demo_alert)
            if res.status_code == 200:
                st.session_state["current_incident"] = res.json()
                st.success("Demo incident triaged successfully!")
                st.rerun()
            else:
                st.error(f"Alert failed: {res.text}")
        except Exception as e:
            st.error(f"Error triggering alert: {e}")

st.title("⚡ BlastRadius Agent — Infrastructure Intelligence")
st.markdown("*Autonomous Infrastructure Incident Triage & Cascading Failure Remediation powered by FalkorDB graph traversal.*")

# Persistent Simulation & Safety Notice
st.warning("🛡️ **Simulation Only Notice:** All remediation actions, state mutations, and telemetry are strictly simulated against a local topology adapter. No production infrastructure, cloud clusters, or real databases are modified.")

# Load Graph Overview for Topology & Metrics
try:
    topo_res = requests.get(f"{API_BASE}/graph/overview").json()
    nodes = topo_res.get("nodes", [])
    edges = topo_res.get("edges", [])
except Exception:
    nodes, edges = [], []

# Fetch active incidents
try:
    inc_list = requests.get(f"{API_BASE}/incidents").json()
except Exception:
    inc_list = []

# Top KPI Row
kpi1, kpi2, kpi3, kpi4 = st.columns(4)
with kpi1:
    st.metric("Total Topology Nodes", len(nodes))
with kpi2:
    st.metric("Connected Dependencies", len(edges))
with kpi3:
    active_incidents = len(inc_list)
    st.metric("Active Incidents", active_incidents)
with kpi4:
    curr_inc = st.session_state.get("current_incident")
    if curr_inc:
        sla_exp = curr_inc.get("blast_radius", {}).get("sla_exposure_minutes", 0)
        st.metric("Potential SLA Exposure", f"{sla_exp} mins (Demo Threshold)")
    else:
        st.metric("Potential SLA Exposure", "0 mins")

# Tabs for workflow
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
    if not curr_inc:
        st.info("💡 No incident active. Click **'Run Demo Incident: DB Saturation'** in the sidebar to simulate an incident triage.")
    else:
        inc_id = curr_inc.get("incident_id")
        alert = curr_inc.get("alert", {})
        blast = curr_inc.get("blast_radius", {})
        root_causes = curr_inc.get("root_cause_candidates", [])
        plan = curr_inc.get("remediation_plan", {})
        
        # Incident Banner
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

            # Dependency paths
            with st.expander("📍 View Graph Traversal Dependency Paths", expanded=True):
                for p in blast.get("paths", []):
                    st.code(" ➔ ".join(p) if isinstance(p, list) else str(p), language="text")

        with col_right:
            st.subheader("👥 Impacted Customers by Tier")
            custs = blast.get("impacted_customers", [])
            tier_summary = blast.get("impacted_customer_tiers", {})
            
            # Show summary counts
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
            
            # Download JSON Report
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
                        rem_res = requests.post(f"{API_BASE}/incidents/{inc_id}/remediate", json={"approved": True})
                        if rem_res.status_code == 200:
                            st.success("Remediation successfully simulated, applied, and verified against graph state!")
                            # Refresh incident
                            updated_inc = requests.get(f"{API_BASE}/incidents/{inc_id}").json()
                            st.session_state["current_incident"] = updated_inc
                            st.rerun()
                        else:
                            st.error(f"Remediation error: {rem_res.text}")
                    except Exception as e:
                        st.error(f"Execution error: {e}")

        with col_act2:
            st.markdown("&nbsp;")
            if st.button("⏪ Rollback Simulated Actions", use_container_width=True):
                try:
                    rb_res = requests.post(f"{API_BASE}/incidents/{inc_id}/rollback")
                    if rb_res.status_code == 200:
                        st.success("State successfully rolled back to pre-incident snapshot!")
                        updated_inc = requests.get(f"{API_BASE}/incidents/{inc_id}").json()
                        st.session_state["current_incident"] = updated_inc
                        st.rerun()
                    else:
                        st.error(f"Rollback error: {rb_res.text}")
                except Exception as e:
                    st.error(f"Rollback failed: {e}")

        # Audit History
        st.subheader("📜 Incident Audit History")
        audit_history = curr_inc.get("audit_history", [])
        if audit_history:
            st.dataframe(pd.DataFrame(audit_history), use_container_width=True)

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
                res = requests.post(f"{API_BASE}/alert", json=custom_payload)
                if res.status_code == 200:
                    st.session_state["current_incident"] = res.json()
                    st.success("Custom alert triaged!")
                    st.rerun()
                else:
                    st.error(f"Triage failed: {res.text}")
            except Exception as e:
                st.error(f"Error submitting alert: {e}")
