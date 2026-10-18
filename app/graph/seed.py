"""
Seed realistic infrastructure topology into FalkorDB.
Nodes:
- Ingress: api-gateway
- Services: auth-service, user-profile-service, payment-service, order-service, notification-service, reporting-service, fraud-detector
- Databases: user-creds-postgres, user-profile-replica, orders-mongo, analytics-warehouse
- Queues: notification-events-queue, payment-audit-stream
- Fallbacks: auth-redis-cache
- Customers: cust-acme-corp (Tier-1), cust-fintech-pro (Tier-1), cust-globex (Tier-2), cust-byte-retail (Tier-3)

Incident Scenario:
user-creds-postgres experiences high CPU and connection-pool saturation.
"""
from app.graph.client import falkor_client

SEED_NODES = [
    # Ingress
    ("Ingress", {"name": "api-gateway", "status": "healthy", "region": "us-east-1"}),
    
    # Core Services
    ("Service", {"name": "auth-service", "status": "healthy", "owner_team": "security-core", "criticality": "tier-1", "latency_ms": 12.5, "error_rate": 0.005, "health_score": 0.99}),
    ("Service", {"name": "user-profile-service", "status": "healthy", "owner_team": "user-platform", "criticality": "tier-1", "latency_ms": 15.0, "error_rate": 0.008, "health_score": 0.98}),
    ("Service", {"name": "payment-service", "status": "healthy", "owner_team": "checkout-payments", "criticality": "tier-1", "latency_ms": 35.0, "error_rate": 0.002, "health_score": 0.99}),
    ("Service", {"name": "order-service", "status": "healthy", "owner_team": "commerce", "criticality": "tier-1", "latency_ms": 28.0, "error_rate": 0.010, "health_score": 0.97}),
    ("Service", {"name": "notification-service", "status": "healthy", "owner_team": "growth", "criticality": "tier-2", "latency_ms": 50.0, "error_rate": 0.015, "health_score": 0.95}),
    ("Service", {"name": "reporting-service", "status": "healthy", "owner_team": "business-intel", "criticality": "tier-3", "latency_ms": 120.0, "error_rate": 0.020, "health_score": 0.92}),
    ("Service", {"name": "fraud-detector", "status": "healthy", "owner_team": "risk", "criticality": "tier-2", "latency_ms": 40.0, "error_rate": 0.005, "health_score": 0.98}),

    # Databases
    ("Database", {"name": "user-creds-postgres", "type": "PostgreSQL", "status": "healthy", "read_only": False, "cpu_percent": 34.0, "connection_pool_usage": 0.45}),
    ("Database", {"name": "user-profile-replica", "type": "PostgreSQL", "status": "healthy", "read_only": True, "cpu_percent": 18.0, "connection_pool_usage": 0.20}),
    ("Database", {"name": "orders-mongo", "type": "MongoDB", "status": "healthy", "read_only": False, "cpu_percent": 42.0, "connection_pool_usage": 0.50}),
    ("Database", {"name": "analytics-warehouse", "type": "ClickHouse", "status": "healthy", "read_only": True, "cpu_percent": 25.0, "connection_pool_usage": 0.30}),
    
    # Fallback Cache / Node
    ("Service", {"name": "auth-redis-cache", "status": "healthy", "owner_team": "security-core", "criticality": "tier-2", "latency_ms": 2.0, "error_rate": 0.001, "health_score": 1.0}),

    # Queues
    ("Queue", {"name": "notification-events-queue", "status": "healthy", "backlog": 120, "consumer_lag": 5}),
    ("Queue", {"name": "payment-audit-stream", "status": "healthy", "backlog": 45, "consumer_lag": 2}),

    # Customers
    ("Customer", {"id": "cust-acme-corp", "name": "Acme Global Enterprise", "tier": "Tier-1", "sla_minutes": 15, "business_criticality": "mission-critical"}),
    ("Customer", {"id": "cust-fintech-pro", "name": "Fintech Pro Payments", "tier": "Tier-1", "sla_minutes": 15, "business_criticality": "mission-critical"}),
    ("Customer", {"id": "cust-globex", "name": "Globex Logistics", "tier": "Tier-2", "sla_minutes": 60, "business_criticality": "high"}),
    ("Customer", {"id": "cust-byte-retail", "name": "Byte Retail LLC", "tier": "Tier-3", "sla_minutes": 240, "business_criticality": "standard"}),
]

SEED_EDGES = [
    # Customer routing to Ingress and Services
    ("cust-acme-corp", "ROUTED_THROUGH", "api-gateway", {"weight": 1.0}),
    ("cust-fintech-pro", "ROUTED_THROUGH", "api-gateway", {"weight": 1.0}),
    ("cust-globex", "ROUTED_THROUGH", "api-gateway", {"weight": 1.0}),
    ("cust-byte-retail", "ROUTED_THROUGH", "api-gateway", {"weight": 1.0}),

    # Ingress to services
    ("api-gateway", "ROUTES_TO", "auth-service", {"protocol": "https", "weight": 1.0, "timeout_ms": 2000}),
    ("api-gateway", "ROUTES_TO", "order-service", {"protocol": "https", "weight": 1.0, "timeout_ms": 3000}),
    ("api-gateway", "ROUTES_TO", "reporting-service", {"protocol": "https", "weight": 1.0, "timeout_ms": 5000}),

    # Service-to-Service CALLS
    ("order-service", "CALLS", "auth-service", {"protocol": "grpc", "timeout_ms": 1500, "circuit_broken": False}),
    ("order-service", "CALLS", "payment-service", {"protocol": "grpc", "timeout_ms": 3000, "circuit_broken": False}),
    ("order-service", "CALLS", "user-profile-service", {"protocol": "grpc", "timeout_ms": 1500, "circuit_broken": False}),
    ("payment-service", "CALLS", "auth-service", {"protocol": "grpc", "timeout_ms": 1500, "circuit_broken": False}),
    ("payment-service", "CALLS", "fraud-detector", {"protocol": "grpc", "timeout_ms": 800, "circuit_broken": False}),

    # Database Reads & Writes
    ("auth-service", "WRITES_TO", "user-creds-postgres", {"pool_size": 20, "timeout_ms": 2000}),
    ("auth-service", "READS_FROM", "user-creds-postgres", {"pool_size": 50, "timeout_ms": 1000}),
    ("user-profile-service", "READS_FROM", "user-creds-postgres", {"pool_size": 30, "timeout_ms": 1000}),
    ("user-profile-service", "READS_FROM", "user-profile-replica", {"pool_size": 40, "timeout_ms": 800}),
    ("order-service", "WRITES_TO", "orders-mongo", {"pool_size": 25, "timeout_ms": 2000}),
    ("reporting-service", "READS_FROM", "analytics-warehouse", {"pool_size": 10, "timeout_ms": 10000}),

    # Fallback paths
    ("auth-service", "FALLBACK_TO", "auth-redis-cache", {"protocol": "redis", "circuit_broken": False, "priority": 1}),
    ("user-profile-service", "FALLBACK_TO", "user-profile-replica", {"protocol": "postgres-ro", "circuit_broken": False, "priority": 1}),

    # Queues
    ("order-service", "PUBLISHES_TO", "notification-events-queue", {"batch_size": 10}),
    ("notification-service", "CONSUMES_FROM", "notification-events-queue", {"concurrency": 4}),
    ("payment-service", "PUBLISHES_TO", "payment-audit-stream", {"durability": "sync"}),
]

def seed_database(reset: bool = True):
    """
    Idempotent seeding function.
    Populates both FalkorDB (if available) and the in-memory graph adapter.
    """
    # 1. Always update memory graph adapter for deterministic testing and instant availability
    mem = falkor_client.memory_graph
    if reset:
        mem.nodes.clear()
        mem.edges.clear()

    for label, props in SEED_NODES:
        mem.add_node([label], dict(props))

    for src, rel, dst, props in SEED_EDGES:
        mem.add_edge(src, rel, dst, dict(props))

    # 2. If FalkorDB client is connected, also populate real FalkorDB
    if falkor_client.is_connected and not falkor_client.use_memory_fallback:
        try:
            if reset:
                falkor_client.query("MATCH (n) DETACH DELETE n")
            
            # Create nodes idempotently via MERGE
            for label, props in SEED_NODES:
                ident = props.get("name") or props.get("id")
                prop_assign = ", ".join([f"n.{k} = ${k}" for k in props.keys()])
                q = f"MERGE (n:{label} {{name: $name}}) ON CREATE SET {prop_assign} ON MATCH SET {prop_assign}"
                if "id" in props:
                    q = f"MERGE (n:{label} {{id: $id}}) ON CREATE SET {prop_assign} ON MATCH SET {prop_assign}"
                falkor_client.query(q, props)

            # Create edges idempotently via MERGE
            for src, rel, dst, props in SEED_EDGES:
                edge_props = ", ".join([f"r.{k} = ${k}" for k in props.keys()])
                set_clause = f"ON CREATE SET {edge_props} ON MATCH SET {edge_props}" if edge_props else ""
                q = f"""
                MATCH (a), (b)
                WHERE (a.name = $src OR a.id = $src) AND (b.name = $dst OR b.id = $dst)
                MERGE (a)-[r:{rel}]->(b)
                {set_clause}
                """
                params = {"src": src, "dst": dst, **props}
                falkor_client.query(q, params)
        except Exception as e:
            logger.warning(f"Failed to seed live FalkorDB instance: {e}. In-memory graph adapter is active.")

    return {
        "status": "success",
        "nodes_seeded": len(SEED_NODES),
        "edges_seeded": len(SEED_EDGES),
        "connected_to_falkordb": falkor_client.is_connected and not falkor_client.use_memory_fallback
    }
