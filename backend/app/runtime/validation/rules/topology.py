"""Pass 2 - Topology: entry/output, cycles, reachability, dead ends,
parallel/merge structure and parallel-merge pairing."""

from app.domain.workflows.graph import NodeType, WorkflowGraph

from ..result import ValidationIssue
from ..codes import ValidationCode
from ..context import ValidationContext
from ..graph_index import GraphIndex


def _is_data(node_type: str, subtype: str) -> bool:
    return node_type == NodeType.DATA and subtype in {"input", "output"}


def validate_topology(graph: WorkflowGraph, index: GraphIndex, context: ValidationContext) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    entry = index.entry_node_ids()
    if len(entry) == 0:
        issues.append(
            ValidationIssue(
                code=ValidationCode.MISSING_INPUT_NODE,
                severity="error",
                message="Workflow requires exactly one Data Input node",
                field="nodes[]",
            )
        )
    elif len(entry) > 1:
        issues.append(
            ValidationIssue(
                code=ValidationCode.MULTIPLE_INPUT_NODES,
                severity="error",
                message="Workflow must have a single Data Input node",
                field="nodes[]",
                details={"node_ids": entry},
            )
        )
    else:
        for edge in index.incoming_edges(entry[0]):
            issues.append(
                ValidationIssue(
                    code=ValidationCode.INVALID_INPUT_NODE_EDGE,
                    severity="error",
                    message=f"Data Input node must not have incoming edges",
                    edge_id=edge.id,
                    node_id=entry[0],
                    field="edges[]",
                )
            )

    outputs = index.output_node_ids()
    if len(outputs) == 0:
        issues.append(
            ValidationIssue(
                code=ValidationCode.MISSING_OUTPUT_NODE,
                severity="error",
                message="Workflow requires at least one Data Output node",
                field="nodes[]",
            )
        )
    else:
        for output in outputs:
            for edge in index.outgoing_edges(output):
                issues.append(
                    ValidationIssue(
                        code=ValidationCode.INVALID_OUTPUT_NODE_EDGE,
                        severity="error",
                        message=f"Data Output node must not have outgoing edges",
                        edge_id=edge.id,
                        node_id=output,
                        field="edges[]",
                    )
                )

    if index.has_cycle():
        issues.append(
            ValidationIssue(
                code=ValidationCode.UNSUPPORTED_CYCLE,
                severity="error",
                message="Workflow graph must be a DAG; cycles are not supported in V1",
                field="edges[]",
                details={"node_ids": sorted(index.cycle_nodes())},
            )
        )

    if len(entry) == 1 and not index.has_cycle():
        reachable = index.reachable_from(entry)
        for node in graph.nodes:
            if node.id not in reachable:
                issues.append(
                    ValidationIssue(
                        code=ValidationCode.UNREACHABLE_NODE,
                        severity="error",
                        message=f"Node {node.name or node.id!r} is not reachable from the Workflow Input",
                        node_id=node.id,
                        field="nodes[]",
                    )
                )

    if outputs and not index.has_cycle() and len(entry) == 1:
        reverse_reachable: set[str] = set()
        for output in outputs:
            reverse_reachable.add(output)
            reverse_reachable.update(index.ancestors(output))
        reachable = index.reachable_from(entry)
        for node in graph.nodes:
            if node.id not in reachable:
                continue
            if node.id in reverse_reachable:
                continue
            if _is_data(node.type, node.subtype):
                continue
            if node.type == NodeType.LOGIC and node.subtype in {"condition", "parallel", "merge"}:
                # These get more specific structural errors elsewhere.
                continue
            issues.append(
                ValidationIssue(
                    code=ValidationCode.DEAD_END_BRANCH,
                    severity="error",
                    message=f"Node {node.name or node.id!r} cannot reach any Data Output",
                    node_id=node.id,
                    field="nodes[]",
                )
            )

    _validate_parallel_merge(graph, index, issues)

    return issues


def _validate_parallel_merge(graph: WorkflowGraph, index: GraphIndex, issues: list[ValidationIssue]) -> None:
    for node in graph.nodes:
        if node.type != NodeType.LOGIC:
            continue
        if node.subtype == "parallel":
            outgoing = index.outgoing_edges(node.id)
            if len(outgoing) < 2:
                issues.append(
                    ValidationIssue(
                        code=ValidationCode.INVALID_PARALLEL,
                        severity="error",
                        message=f"Parallel node requires at least 2 outgoing branches",
                        node_id=node.id,
                        field="config",
                        details={"outgoing": len(outgoing)},
                    )
                )
            incoming = index.incoming_edges(node.id)
            if len(incoming) != 1:
                issues.append(
                    ValidationIssue(
                        code=ValidationCode.INVALID_PARALLEL,
                        severity="error",
                        message=f"Parallel node requires exactly 1 incoming edge",
                        node_id=node.id,
                        field="edges[]",
                        details={"incoming": len(incoming)},
                    )
                )
        elif node.subtype == "merge":
            if node.config.get("strategy") != "all":
                issues.append(
                    ValidationIssue(
                        code=ValidationCode.INVALID_MERGE,
                        severity="error",
                        message="Merge node only supports strategy 'all' in V1",
                        node_id=node.id,
                        field="config.strategy",
                    )
                )
            incoming = index.incoming_edges(node.id)
            if len(incoming) < 2:
                issues.append(
                    ValidationIssue(
                        code=ValidationCode.INVALID_MERGE,
                        severity="error",
                        message=f"Merge node requires at least 2 incoming edges",
                        node_id=node.id,
                        field="edges[]",
                        details={"incoming": len(incoming)},
                    )
                )
            outgoing = index.outgoing_edges(node.id)
            if len(outgoing) != 1:
                issues.append(
                    ValidationIssue(
                        code=ValidationCode.INVALID_MERGE,
                        severity="error",
                        message="Merge node requires exactly 1 outgoing edge",
                        node_id=node.id,
                        field="edges[]",
                        details={"outgoing": len(outgoing)},
                    )
                )

    if not index.has_cycle():
        _validate_parallel_merge_pairing(graph, index, issues)


def _validate_parallel_merge_pairing(graph: WorkflowGraph, index: GraphIndex, issues: list[ValidationIssue]) -> None:
    """Detect branches of a Parallel that bypass its Merge join.

    For a Parallel P that has at least one Merge descendant, if an Output is
    reachable from P without crossing any Merge node, a branch bypasses the
    join. This is a conservative heuristic (strict structured-concurrency
    analysis is deferred); it deterministically catches the common mistake.
    """
    outputs = set(index.output_node_ids())
    for node in graph.nodes:
        if node.type != NodeType.LOGIC or node.subtype != "parallel":
            continue
        merge_descendants = {nid for nid in index.descendants(node.id) if (index.node(nid).subtype if index.node(nid) else "") == "merge"}
        if not merge_descendants:
            continue
        # Reachability that does not expand beyond merge nodes.
        merge_free: set[str] = set()
        stack = [edge.target for edge in index.outgoing_edges(node.id)]
        while stack:
            current = stack.pop()
            if current in merge_free:
                continue
            merge_free.add(current)
            current_node = index.node(current)
            if current_node is not None and current_node.type == NodeType.LOGIC and current_node.subtype == "merge":
                continue
            for edge in index.outgoing_edges(current):
                if edge.target not in merge_free:
                    stack.append(edge.target)
        bypassed = sorted(merge_free & outputs)
        if bypassed:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.INVALID_PARALLEL_MERGE_STRUCTURE,
                    severity="error",
                    message="A Parallel branch bypasses its Merge join and reaches an Output directly",
                    node_id=node.id,
                    field="edges[]",
                    details={"output_nodes": bypassed},
                )
            )
