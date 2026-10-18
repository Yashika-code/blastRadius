"""
Cypher query templates and parameterized FalkorDB graph access methods.
Handles deterministic traversals, dependency tracing, blast-radius calculations,
and customer impact analysis.
"""
from typing import Dict, Any, List, Optional
from app.graph.client import falkor_client
from app.models.schemas import ImpactedCustomer, FallbackPath

def get_graph_overview() -> Dict[str, Any]:
    """Returns all nodes and edges for visualization and health monitoring."""
    nodes = []
    edges = []
    
    # In-memory graph fast path
    mem = falkor_client.memory_graph
    if falkor_client.use_memory_fallback or not falkor_client.is_connected:
        for name, data in mem.nodes.items():
            nodes.append({
                "id": name,
                "label": name,
                "type": data["labels"][0] if data["labels"] else "Component",
                **data["properties"]
            })
        for e in mem.edges:
            edges.append({
                "from": e["src"],
                "to": e["dst"],
                "label": e["relation"],
                **e["properties"]
            })
        return {"nodes": nodes, "edges": edges, "mode": "in-memory"}
    
    # Real FalkorDB Cypher queries
    try:
        n_res = falkor_client.query("MATCH (n) RETURN n, labels(n)")
        for row in n_res.result_set:
            node_obj = row[0]
            labels = row[1] if len(row) > 1 else ["Component"]
            props = node_obj.properties if hasattr(node_obj, "properties") else {}
            node_id = props.get("name") or props.get("id") or str(id(node_obj))
            nodes.append({
                "id": node_id,
                "label": node_id,
                "type": labels[0] if labels else "Component",
                **props
            })

        e_res = falkor_client.query("MATCH (a)-[r]->(b) RETURN a.name, a.id, type(r), b.name, b.id, properties(r)")
        for row in e_res.result_set:
            src = row[0] or row[1]
            rel_type = row[2]
            dst = row[3] or row[4]
            props = row[5] if len(row) > 5 and isinstance(row[5], dict) else {}
            edges.append({
                "from": src,
                "to": dst,
                "label": rel_type,
                **props
            })
        return {"nodes": nodes, "edges": edges, "mode": "falkordb"}
    except Exception:
        # Fallback to in-memory representation
        return get_graph_overview()

def find_component(name: str) -> Optional[Dict[str, Any]]:
    """Look up a specific node by name or id."""
    # Check in-memory fast lookup
    if name in falkor_client.memory_graph.nodes:
        data = falkor_client.memory_graph.nodes[name]
        label = data["labels"][0] if data["labels"] else "Component"
        res = dict(data["properties"])
        res["node_label"] = label
        if "type" not in res:
            res["type"] = label
        return res
    
    # Check FalkorDB
    if falkor_client.is_connected and not falkor_client.use_memory_fallback:
        try:
            res = falkor_client.query("MATCH (n) WHERE n.name = $name OR n.id = $name RETURN n, labels(n)", {"name": name})
            if res.result_set:
                node_obj = res.result_set[0][0]
                labels = res.result_set[0][1]
                return {
                    "name": name,
                    "type": labels[0] if labels else "Component",
                    **getattr(node_obj, "properties", {})
                }
        except Exception:
            pass
    return None

def trace_upstream_dependencies(name: str, max_hops: int = 3) -> List[Dict[str, Any]]:
    """
    Find components that depend on 'name' (i.e., (x)-[*1..max_hops]->(name)).
    These are the upstream callers that suffer when 'name' fails.
    """
    # 1. FalkorDB live Cypher traversal when connected
    if falkor_client.is_connected and not falkor_client.use_memory_fallback:
        try:
            cypher = f"""
            MATCH (src)-[r*1..{max_hops}]->(target)
            WHERE (target.name = $name OR target.id = $name) AND src <> target
            RETURN DISTINCT src.name, src.id, labels(src), length(r), properties(src)
            ORDER BY length(r) ASC
            """
            res = falkor_client.query(cypher, {"name": name})
            upstream_list = []
            seen = set()
            for row in res.result_set:
                comp_name = row[0] or row[1]
                if not comp_name or comp_name in seen or comp_name == name:
                    continue
                seen.add(comp_name)
                labels = row[2] if len(row) > 2 and row[2] else ["Service"]
                hops = row[3] if len(row) > 3 else 1
                props = row[4] if len(row) > 4 and isinstance(row[4], dict) else {}
                upstream_list.append({
                    "component": comp_name,
                    "type": labels[0] if labels else "Service",
                    "hops": hops,
                    "path": [f"({comp_name})-[*1..{hops}]->({name})"],
                    "properties": props
                })
            return upstream_list
        except Exception:
            pass

    # 2. In-memory graph fallback
    mem = falkor_client.memory_graph
    visited = set()
    upstream_list = []
    queue = [(name, 0, [])]  # curr_node, depth, path
    
    # Pre-build reverse adjacency map
    rev_adj: Dict[str, List[Dict[str, Any]]] = {}
    for e in mem.edges:
        dst = e["dst"]
        if dst not in rev_adj:
            rev_adj[dst] = []
        rev_adj[dst].append(e)

    while queue:
        curr, depth, path = queue.pop(0)
        if depth >= max_hops:
            continue
        
        for edge in rev_adj.get(curr, []):
            src = edge["src"]
            new_path = path + [f"({src})-[{edge['relation']}]->({curr})"]
            if src not in visited and src != name:
                visited.add(src)
                node_props = mem.nodes.get(src, {}).get("properties", {})
                node_type = mem.nodes.get(src, {}).get("labels", ["Service"])[0]
                upstream_list.append({
                    "component": src,
                    "type": node_type,
                    "hops": depth + 1,
                    "path": new_path,
                    "properties": node_props
                })
                queue.append((src, depth + 1, new_path))
            elif src in visited:
                queue.append((src, depth + 1, new_path))
                
    return upstream_list

def trace_downstream_dependencies(name: str, max_hops: int = 3) -> List[Dict[str, Any]]:
    """
    Find components that 'name' calls or depends on (i.e. (name)-[*1..max_hops]->(x)).
    """
    # 1. FalkorDB live Cypher traversal when connected
    if falkor_client.is_connected and not falkor_client.use_memory_fallback:
        try:
            cypher = f"""
            MATCH (src)-[r*1..{max_hops}]->(dst)
            WHERE (src.name = $name OR src.id = $name) AND dst <> src
            RETURN DISTINCT dst.name, dst.id, labels(dst), length(r), properties(dst)
            ORDER BY length(r) ASC
            """
            res = falkor_client.query(cypher, {"name": name})
            downstream_list = []
            seen = set()
            for row in res.result_set:
                comp_name = row[0] or row[1]
                if not comp_name or comp_name in seen or comp_name == name:
                    continue
                seen.add(comp_name)
                labels = row[2] if len(row) > 2 and row[2] else ["Service"]
                hops = row[3] if len(row) > 3 else 1
                props = row[4] if len(row) > 4 and isinstance(row[4], dict) else {}
                downstream_list.append({
                    "component": comp_name,
                    "type": labels[0] if labels else "Service",
                    "hops": hops,
                    "path": [f"({name})-[*1..{hops}]->({comp_name})"],
                    "properties": props
                })
            return downstream_list
        except Exception:
            pass

    # 2. In-memory graph fallback
    mem = falkor_client.memory_graph
    visited = set()
    downstream_list = []
    queue = [(name, 0, [])]

    adj: Dict[str, List[Dict[str, Any]]] = {}
    for e in mem.edges:
        src = e["src"]
        if src not in adj:
            adj[src] = []
        adj[src].append(e)

    while queue:
        curr, depth, path = queue.pop(0)
        if depth >= max_hops:
            continue
        for edge in adj.get(curr, []):
            dst = edge["dst"]
            new_path = path + [f"({curr})-[{edge['relation']}]->({dst})"]
            if dst not in visited and dst != name:
                visited.add(dst)
                node_props = mem.nodes.get(dst, {}).get("properties", {})
                node_type = mem.nodes.get(dst, {}).get("labels", ["Service"])[0]
                downstream_list.append({
                    "component": dst,
                    "type": node_type,
                    "hops": depth + 1,
                    "path": new_path,
                    "properties": node_props
                })
                queue.append((dst, depth + 1, new_path))
    return downstream_list

def find_fallback_paths(name: str) -> List[FallbackPath]:
    """
    Find any defined FALLBACK_TO paths from or around the component.
    """
    if falkor_client.is_connected and not falkor_client.use_memory_fallback:
        try:
            cypher = """
            MATCH (src)-[r:FALLBACK_TO]->(dst)
            RETURN src.name, src.id, dst.name, dst.id, properties(r), properties(dst)
            """
            res = falkor_client.query(cypher)
            fallbacks = []
            for row in res.result_set:
                src = row[0] or row[1]
                dst = row[2] or row[3]
                rel_props = row[4] if len(row) > 4 and isinstance(row[4], dict) else {}
                dst_props = row[5] if len(row) > 5 and isinstance(row[5], dict) else {}
                fallbacks.append(FallbackPath(
                    from_service=src,
                    to_service=dst,
                    protocol=rel_props.get("protocol", "http"),
                    circuit_broken=rel_props.get("circuit_broken", False),
                    status=dst_props.get("status", "healthy")
                ))
            if fallbacks:
                return fallbacks
        except Exception:
            pass

    mem = falkor_client.memory_graph
    fallbacks = []
    for e in mem.edges:
        if e["relation"] == "FALLBACK_TO":
            target_node = mem.nodes.get(e["dst"], {})
            status = target_node.get("properties", {}).get("status", "healthy")
            fallbacks.append(FallbackPath(
                from_service=e["src"],
                to_service=e["dst"],
                protocol=e["properties"].get("protocol", "http"),
                circuit_broken=e["properties"].get("circuit_broken", False),
                status=status
            ))
    return fallbacks

def get_impacted_customers(name: str) -> List[ImpactedCustomer]:
    """
    Calculates exact customers affected by failure of 'name'.
    Traces upstream to ingress and customer nodes.
    Deduplicates and groups by customer tier.
    """
    upstream = trace_upstream_dependencies(name, max_hops=4)
    impacted_services = {u["component"] for u in upstream}
    impacted_services.add(name)

    if falkor_client.is_connected and not falkor_client.use_memory_fallback:
        try:
            cypher = """
            MATCH (c:Customer)-[:ROUTED_THROUGH]->(ingress)-[:ROUTES_TO|CALLS*1..3]->(target)
            WHERE (target.name = $name OR target.id = $name)
            RETURN DISTINCT c.id, c.name, c.tier, c.sla_minutes, c.business_criticality, ingress.name, target.name
            """
            res = falkor_client.query(cypher, {"name": name})
            customers = {}
            for row in res.result_set:
                cid = row[0] or row[1]
                cname = row[1] or cid
                tier = row[2] or "Tier-2"
                sla = row[3] if row[3] is not None else 60
                crit = row[4] or "medium"
                ingress = row[5] or "ingress"
                target = row[6] or name
                customers[cid] = ImpactedCustomer(
                    id=cid,
                    name=cname,
                    tier=tier,
                    sla_minutes=sla,
                    business_criticality=crit,
                    path_summary=f"Customer ({cid}) -> {ingress} -> ... -> {target}"
                )
            if customers:
                return list(customers.values())
        except Exception:
            pass

    mem = falkor_client.memory_graph
    customers: Dict[str, ImpactedCustomer] = {}

    for e in mem.edges:
        if e["relation"] == "ROUTED_THROUGH":
            cust_id = e["src"]
            entry_point = e["dst"]  # e.g., api-gateway
            for e2 in mem.edges:
                if e2["src"] == entry_point and e2["dst"] in impacted_services:
                    cust_props = mem.nodes.get(cust_id, {}).get("properties", {})
                    if cust_id not in customers:
                        customers[cust_id] = ImpactedCustomer(
                            id=cust_id,
                            name=cust_props.get("name", cust_id),
                            tier=cust_props.get("tier", "Tier-2"),
                            sla_minutes=cust_props.get("sla_minutes", 60),
                            business_criticality=cust_props.get("business_criticality", "medium"),
                            path_summary=f"Customer ({cust_id}) -> {entry_point} -> {e2['dst']} -> {name}"
                        )
    return list(customers.values())
