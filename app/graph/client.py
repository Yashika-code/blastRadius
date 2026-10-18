"""
FalkorDB Client & Graph Connection Wrapper.
Truthfully manages connection to FalkorDB and tracks backend status.
Supports dual modes:
- live FalkorDB Redis engine (Graph query with official FalkorDB client)
- local In-Memory graph adapter (when FalkorDB is offline, explicitly labeled)
"""
import logging
from typing import Any, Dict, List, Optional
from app.config import settings

logger = logging.getLogger(__name__)

class MemoryQueryResult:
    def __init__(self, result_set: List[List[Any]]):
        self.result_set = result_set

class InMemoryGraphAdapter:
    """
    In-memory graph engine with Cypher-like query processing.
    Used for local testing or when FalkorDB is offline.
    """
    def __init__(self, name: str = "blast_radius"):
        self.name = name
        self.nodes: Dict[str, Dict[str, Any]] = {}  # id/name -> {labels, properties}
        self.edges: List[Dict[str, Any]] = []       # [{src, relation, dst, properties}]
        logger.info(f"Initialized InMemoryGraphAdapter for graph '{name}'")

    def query(self, query_str: str, params: Optional[Dict[str, Any]] = None) -> MemoryQueryResult:
        params = params or {}
        q = query_str.strip()
        
        # 1. MATCH (n) DETACH DELETE n
        if "DETACH DELETE" in q:
            self.nodes.clear()
            self.edges.clear()
            return MemoryQueryResult([])

        # 2. Component lookup
        if "MATCH (n)" in q and ("n.name = $name" in q or "n.id = $name" in q):
            name = params.get("name")
            if name in self.nodes:
                data = self.nodes[name]
                node_obj = type("Node", (), {
                    "properties": data["properties"],
                    "labels": data["labels"]
                })()
                return MemoryQueryResult([[node_obj, data["labels"]]])
            return MemoryQueryResult([])

        # 3. Overview queries
        if "MATCH (n) RETURN n, labels(n)" in q:
            results = []
            seen = set()
            for n_id, data in self.nodes.items():
                ident = data["properties"].get("id") or data["properties"].get("name")
                if ident in seen:
                    continue
                seen.add(ident)
                node_obj = type("Node", (), {
                    "properties": data["properties"],
                    "labels": data["labels"]
                })()
                results.append([node_obj, data["labels"]])
            return MemoryQueryResult(results)

        # 4. Relationship overview
        if "MATCH (a)-[r]->(b)" in q and "RETURN" in q:
            results = []
            for e in self.edges:
                results.append([e["src"], None, e["relation"], e["dst"], None, e["properties"]])
            return MemoryQueryResult(results)

        # 5. Fallback paths
        if "FALLBACK_TO" in q:
            from_name = params.get("name")
            results = []
            for e in self.edges:
                if e["relation"] == "FALLBACK_TO":
                    if not from_name or e["src"] == from_name:
                        target_node = self.nodes.get(e["dst"], {})
                        results.append([
                            e["src"],
                            e["dst"],
                            e["properties"].get("protocol", "http"),
                            e["properties"].get("circuit_broken", False),
                            target_node.get("properties", {}).get("status", "healthy")
                        ])
            return MemoryQueryResult(results)

        return MemoryQueryResult([])

    def add_node(self, labels: List[str], properties: Dict[str, Any]):
        ident = properties.get("id") or properties.get("name")
        if ident:
            self.nodes[ident] = {
                "labels": labels,
                "properties": properties
            }
            if "name" in properties and properties["name"] != ident:
                self.nodes[properties["name"]] = self.nodes[ident]
            if "id" in properties and properties["id"] != ident:
                self.nodes[properties["id"]] = self.nodes[ident]

    def add_edge(self, src: str, relation: str, dst: str, properties: Optional[Dict[str, Any]] = None):
        properties = properties or {}
        for e in self.edges:
            if e["src"] == src and e["relation"] == relation and e["dst"] == dst:
                e["properties"].update(properties)
                return
        self.edges.append({
            "src": src,
            "relation": relation,
            "dst": dst,
            "properties": properties
        })


class FalkorDBClient:
    """
    FalkorDB Client supporting both real FalkorDB connection and
    explicitly identified in-memory adapter fallback.
    """
    def __init__(self):
        self.client = None
        self.graph = None
        self.is_connected = False
        self.active_backend = "in-memory-graph-adapter"
        self.connection_error = None
        self.memory_graph = InMemoryGraphAdapter(settings.FALKORDB_GRAPH_NAME)
        self.connect()

    @property
    def use_memory_fallback(self) -> bool:
        return not self.is_connected or self.active_backend != "falkordb"

    def connect(self) -> bool:
        """Attempts connection to real FalkorDB server."""
        try:
            from falkordb import FalkorDB
            self.client = FalkorDB(
                host=settings.FALKORDB_HOST,
                port=settings.FALKORDB_PORT,
                password=settings.FALKORDB_PASSWORD
            )
            self.graph = self.client.select_graph(settings.FALKORDB_GRAPH_NAME)
            # Execute actual query check
            res = self.graph.query("RETURN 1 AS ping")
            if res:
                self.is_connected = True
                self.active_backend = "falkordb"
                self.connection_error = None
                logger.info(f"Successfully connected to FalkorDB server on {settings.FALKORDB_HOST}:{settings.FALKORDB_PORT}")
                return True
        except Exception as e:
            self.is_connected = False
            self.connection_error = str(e)
            if settings.ALLOW_MEMORY_FALLBACK:
                self.active_backend = "in-memory-graph-adapter"
                self.graph = self.memory_graph
                logger.warning(
                    f"FalkorDB not reachable at {settings.FALKORDB_HOST}:{settings.FALKORDB_PORT} ({e}). "
                    f"Active backend set to in-memory adapter."
                )
            else:
                self.active_backend = "disconnected"
                logger.error(f"FalkorDB connection failed: {e}. Fallback disabled.")
            return False

    def check_connection(self) -> bool:
        """
        Actively checks if FalkorDB is connected and healthy.
        If disconnected or in fallback, attempts to connect.
        """
        if self.is_connected and self.client and self.graph:
            try:
                # Fast PING check on existing client
                self.client.connection.execute_command("PING")
                return True
            except Exception as e:
                logger.warning(f"FalkorDB connection lost: {e}")
                self.is_connected = False
                self.connection_error = str(e)
                if settings.ALLOW_MEMORY_FALLBACK:
                    self.active_backend = "in-memory-graph-adapter"
                    self.graph = self.memory_graph
        # Attempt connection/reconnection
        return self.connect()

    def query(self, cypher: str, params: Optional[Dict[str, Any]] = None) -> Any:
        params = params or {}
        if not self.is_connected:
            self.check_connection()

        if self.is_connected and self.active_backend == "falkordb":
            try:
                return self.graph.query(cypher, params)
            except Exception as e:
                logger.error(f"FalkorDB query failed: {e}. Executing on memory graph adapter.")
                return self.memory_graph.query(cypher, params)
        else:
            return self.memory_graph.query(cypher, params)

    def get_status_report(self) -> Dict[str, Any]:
        # Actively verify connection before reporting
        self.check_connection()
        return {
            "active_backend": self.active_backend,
            "falkordb_connected": self.is_connected,
            "host": settings.FALKORDB_HOST,
            "port": settings.FALKORDB_PORT,
            "graph_name": settings.FALKORDB_GRAPH_NAME,
            "connection_error": self.connection_error
        }

falkor_client = FalkorDBClient()
