"""
Infrastructure Simulator Adapter.
Applies safe, simulated mutations to graph state and modeled infrastructure.
Never calls real cloud providers or executes destructive actions.
Per-incident snapshot journal for exact state restoration during rollback.
"""
import copy
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from app.graph.client import falkor_client

class InfrastructureSimulator:
    """
    Simulates operational changes (circuit breaker tripping, replica failover,
    fallback cache activation, component degradation/isolation).
    Maintains atomic per-incident snapshots for truthful and complete rollback.
    """
    def __init__(self):
        self.snapshots: Dict[str, Dict[str, Any]] = {}
        self.execution_audit_log = []

    def capture_snapshot(self, incident_id: str):
        """Saves current graph state for exact rollback."""
        mem = falkor_client.memory_graph
        self.snapshots[incident_id] = {
            "nodes": copy.deepcopy(mem.nodes),
            "edges": copy.deepcopy(mem.edges),
            "captured_at": datetime.now(timezone.utc).isoformat()
        }

    def rollback(self, incident_id: str) -> Dict[str, Any]:
        """Restores exact graph state from snapshot."""
        if incident_id not in self.snapshots:
            return {
                "status": "failed",
                "reason": f"No snapshot found for incident {incident_id}. State cannot be restored."
            }
        
        snap = self.snapshots[incident_id]
        mem = falkor_client.memory_graph
        mem.nodes = copy.deepcopy(snap["nodes"])
        mem.edges = copy.deepcopy(snap["edges"])
        
        audit_entry = {
            "incident_id": incident_id,
            "action": "ROLLBACK",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "success",
            "simulated": True
        }
        self.execution_audit_log.append(audit_entry)
        return {
            "status": "success",
            "message": f"Successfully rolled back simulated state for incident {incident_id} to pre-remediation snapshot.",
            "restored_at": datetime.now(timezone.utc).isoformat()
        }

    def execute_action(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes a simulated remediation action with precondition checking and target verification.
        """
        action_type = action.get("action_type")
        target = action.get("target_component")
        mem = falkor_client.memory_graph

        if target not in mem.nodes:
            return {
                "success": False,
                "error": f"Precondition failed: Target component '{target}' does not exist in graph topology."
            }

        timestamp = datetime.now(timezone.utc).isoformat()
        result_msg = ""

        if action_type == "trip_circuit_breaker":
            # Set circuit_broken = True on edges pointing to target
            tripped_count = 0
            for e in mem.edges:
                if e["dst"] == target:
                    e["properties"]["circuit_broken"] = True
                    tripped_count += 1
            if tripped_count == 0:
                return {
                    "success": False,
                    "error": f"Precondition failed: No incoming edges found for '{target}' to trip circuit breaker."
                }
            result_msg = f"[SIMULATION] Tripped circuit breaker on {tripped_count} incoming connection(s) to '{target}'."

        elif action_type == "switch_replica":
            replica_name = "user-profile-replica"
            if replica_name not in mem.nodes:
                return {"success": False, "error": f"Precondition failed: Target replica '{replica_name}' not found."}
            
            replica_props = mem.nodes[replica_name]["properties"]
            if replica_props.get("status") != "healthy":
                return {"success": False, "error": f"Precondition failed: Replica '{replica_name}' is not healthy (status: {replica_props.get('status')})."}

            # Mark replica as active primary
            replica_props["read_only"] = False
            rerouted = 0
            for e in mem.edges:
                if e["dst"] == target and e["relation"] == "READS_FROM":
                    e["dst"] = replica_name
                    rerouted += 1
            result_msg = f"[SIMULATION] Promoted healthy replica '{replica_name}' and redirected {rerouted} read path(s) away from '{target}'."

        elif action_type == "enable_fallback_cache":
            cache_name = "auth-redis-cache"
            if cache_name not in mem.nodes:
                return {"success": False, "error": f"Precondition failed: Fallback cache '{cache_name}' not found."}

            cache_props = mem.nodes[cache_name]["properties"]
            if cache_props.get("status") != "healthy":
                return {"success": False, "error": f"Precondition failed: Fallback cache '{cache_name}' is unhealthy."}

            activated = 0
            for e in mem.edges:
                if e["relation"] == "FALLBACK_TO" and e["dst"] == cache_name:
                    e["properties"]["active"] = True
                    activated += 1
            result_msg = f"[SIMULATION] Activated {activated} fallback route(s) to '{cache_name}'. Read traffic directed to low-latency cache."

        elif action_type == "isolate_component":
            mem.nodes[target]["properties"]["status"] = "isolated"
            result_msg = f"[SIMULATION] Component '{target}' isolated from live traffic routing."

        elif action_type == "adjust_traffic_weight":
            adjusted = 0
            for e in mem.edges:
                if e["dst"] == target and "weight" in e["properties"]:
                    e["properties"]["weight"] = 0.0
                    adjusted += 1
            result_msg = f"[SIMULATION] Traffic weight for '{target}' drained to 0.0 on {adjusted} route(s)."

        else:
            return {"success": False, "error": f"Unknown remediation action type '{action_type}'."}

        # Log audit entry
        audit_entry = {
            "action_id": action.get("action_id"),
            "action_type": action_type,
            "target": target,
            "result": result_msg,
            "timestamp": timestamp,
            "simulated": True
        }
        self.execution_audit_log.append(audit_entry)

        return {
            "success": True,
            "message": result_msg,
            "timestamp": timestamp
        }

infra_simulator = InfrastructureSimulator()
