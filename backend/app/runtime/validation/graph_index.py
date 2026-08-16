"""Graph indexing and graph analysis utilities.

Pure functions over a `WorkflowGraph`. Both the Validation Engine and the
future Runtime reuse these. Results are memoized on the index instance.
"""

from collections import deque
from dataclasses import dataclass, field
from typing import Iterable

from app.domain.workflows.graph import NodeType, WorkflowEdge, WorkflowGraph, WorkflowNode


@dataclass
class GraphIndex:
    graph: WorkflowGraph
    nodes_by_id: dict[str, WorkflowNode]
    edges_by_id: dict[str, WorkflowEdge]
    incoming: dict[str, list[WorkflowEdge]]
    outgoing: dict[str, list[WorkflowEdge]]

    _ancestors: dict[str, frozenset[str]] = field(default_factory=dict, init=False)
    _descendants: dict[str, frozenset[str]] = field(default_factory=dict, init=False)
    _cycle_nodes: frozenset[str] | None = field(default=None, init=False)

    @classmethod
    def build(cls, graph: WorkflowGraph) -> "GraphIndex":
        nodes_by_id = {node.id: node for node in graph.nodes}
        edges_by_id = {edge.id: edge for edge in graph.edges}
        incoming: dict[str, list[WorkflowEdge]] = {node.id: [] for node in graph.nodes}
        outgoing: dict[str, list[WorkflowEdge]] = {node.id: [] for node in graph.nodes}
        for edge in graph.edges:
            incoming.setdefault(edge.target, []).append(edge)
            outgoing.setdefault(edge.source, []).append(edge)
        return cls(graph, nodes_by_id, edges_by_id, incoming, outgoing)

    def node(self, node_id: str) -> WorkflowNode | None:
        return self.nodes_by_id.get(node_id)

    def incoming_edges(self, node_id: str) -> list[WorkflowEdge]:
        return self.incoming.get(node_id, [])

    def outgoing_edges(self, node_id: str) -> list[WorkflowEdge]:
        return self.outgoing.get(node_id, [])

    def ancestors(self, node_id: str) -> frozenset[str]:
        """All nodes that can reach `node_id` through control-flow edges
        (excluding `node_id` itself)."""
        cached = self._ancestors.get(node_id)
        if cached is not None:
            return cached
        seen: set[str] = set()
        stack = [edge.source for edge in self.incoming_edges(node_id)]
        while stack:
            current = stack.pop()
            if current == node_id or current in seen:
                continue
            seen.add(current)
            for edge in self.incoming_edges(current):
                if edge.source not in seen and edge.source != node_id:
                    stack.append(edge.source)
        result = frozenset(seen)
        self._ancestors[node_id] = result
        return result

    def descendants(self, node_id: str) -> frozenset[str]:
        """All nodes reachable from `node_id` (excluding `node_id` itself)."""
        cached = self._descendants.get(node_id)
        if cached is not None:
            return cached
        seen: set[str] = set()
        stack = [edge.target for edge in self.outgoing_edges(node_id)]
        while stack:
            current = stack.pop()
            if current == node_id or current in seen:
                continue
            seen.add(current)
            for edge in self.outgoing_edges(current):
                if edge.target not in seen and edge.target != node_id:
                    stack.append(edge.target)
        result = frozenset(seen)
        self._descendants[node_id] = result
        return result

    def reachable_from(self, start_ids: Iterable[str]) -> set[str]:
        seen: set[str] = set()
        stack = list(start_ids)
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            for edge in self.outgoing_edges(current):
                if edge.target not in seen:
                    stack.append(edge.target)
        return seen

    def cycle_nodes(self) -> frozenset[str]:
        """Nodes participating in a cycle (Kahn topological sort leftover)."""
        if self._cycle_nodes is not None:
            return self._cycle_nodes
        indegree = {node_id: len(self.incoming_edges(node_id)) for node_id in self.nodes_by_id}
        queue = deque(node_id for node_id, degree in indegree.items() if degree == 0)
        while queue:
            current = queue.popleft()
            for edge in self.outgoing_edges(current):
                if edge.target not in indegree:
                    continue
                indegree[edge.target] -= 1
                if indegree[edge.target] == 0:
                    queue.append(edge.target)
        self._cycle_nodes = frozenset(node_id for node_id, degree in indegree.items() if degree > 0)
        return self._cycle_nodes

    def has_cycle(self) -> bool:
        return bool(self.cycle_nodes())

    def entry_node_ids(self) -> list[str]:
        """Data Input nodes = primary Workflow entry."""
        return [
            node.id
            for node in self.graph.nodes
            if node.type == NodeType.DATA and node.subtype == "input"
        ]

    def output_node_ids(self) -> list[str]:
        """Data Output nodes = terminal Workflow outputs."""
        return [
            node.id
            for node in self.graph.nodes
            if node.type == NodeType.DATA and node.subtype == "output"
        ]
