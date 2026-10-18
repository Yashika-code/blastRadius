"""
FalkorDB Cypher Schema definition, indices, and constraints.
"""
from app.graph.client import falkor_client

INDEX_QUERIES = [
    # Node indices for fast lookups
    "CREATE INDEX FOR (s:Service) ON (s.name)",
    "CREATE INDEX FOR (d:Database) ON (d.name)",
    "CREATE INDEX FOR (q:Queue) ON (q.name)",
    "CREATE INDEX FOR (c:Customer) ON (c.id)",
    "CREATE INDEX FOR (i:Ingress) ON (i.name)"
]

def apply_schema():
    """
    Creates indices on nodes for performance. FalkorDB gracefully ignores existing indices.
    """
    if falkor_client.use_memory_fallback:
        return {"status": "success", "mode": "in-memory-adapter"}
    
    results = []
    for q in INDEX_QUERIES:
        try:
            falkor_client.query(q)
            results.append({"query": q, "status": "applied"})
        except Exception as e:
            results.append({"query": q, "status": "ignored_or_error", "detail": str(e)})
    return {"status": "success", "indices": results}
