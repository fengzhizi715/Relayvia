from app.domain.runs.models import NodeRun
from app.domain.runs.service import find_ready_nodes
from app.domain.workflows.graph import parse_workflow_graph
from app.runtime.state_machine import NodeRunStatus


def _graph(nodes: list[dict], edges: list[dict]):
    return parse_workflow_graph({"schema_version": "1.0", "nodes": nodes, "edges": edges, "variables": {}, "metadata": {}})


def _input_node(nid="input"):
    return {"id": nid, "type": "data", "subtype": "input", "name": "Input", "position": {"x": 0, "y": 0}, "config": {"schema": {"type": "object"}}, "input_mapping": {}, "metadata": {}}


def _output_node(nid="output"):
    return {"id": nid, "type": "data", "subtype": "output", "name": "Output", "position": {"x": 300, "y": 0}, "config": {"output_mapping": {}}, "input_mapping": {}, "metadata": {}}


def _agent_node(nid, name=None):
    return {"id": nid, "type": "agent", "subtype": "agent", "name": name or nid, "position": {"x": 100, "y": 0}, "config": {"agent_id": "agent-1"}, "input_mapping": {}, "metadata": {}}


def _edge(eid, source, target):
    return {"id": eid, "source": source, "target": target, "source_handle": None, "target_handle": None, "label": None, "condition": None, "metadata": {}}


def _node_run(run_id, node_id, status):
    return NodeRun(workflow_run_id=run_id, node_id=node_id, node_type="agent", node_subtype="agent", node_name_snapshot=node_id, status=status, attempt=0)


def test_linear_graph_ready_nodes():
    graph = _graph([_input_node(), _agent_node("a"), _agent_node("b"), _output_node()], [_edge("e1", "input", "a"), _edge("e2", "a", "b"), _edge("e3", "b", "output")])
    node_runs = [_node_run("r", "input", NodeRunStatus.COMPLETED.value), _node_run("r", "a", NodeRunStatus.PENDING.value), _node_run("r", "b", NodeRunStatus.PENDING.value), _node_run("r", "output", NodeRunStatus.PENDING.value)]
    assert find_ready_nodes(graph, node_runs) == ["a"]


def test_parallel_graph_exposes_multiple_ready_nodes():
    nodes = [_input_node(), _agent_node("a"), _agent_node("b")]
    nodes.append({"id": "p", "type": "logic", "subtype": "parallel", "name": "P", "position": {"x": 100, "y": 0}, "config": {}, "input_mapping": {}, "metadata": {}})
    nodes.append(_output_node())
    edges = [_edge("e1", "input", "p"), _edge("e2", "p", "a"), _edge("e3", "p", "b")]
    edges.append(_edge("e4", "a", "output"))
    edges.append(_edge("e5", "b", "output"))
    graph = _graph(nodes, edges)
    node_runs = [
        _node_run("r", "input", NodeRunStatus.COMPLETED.value),
        _node_run("r", "p", NodeRunStatus.PENDING.value),
        _node_run("r", "a", NodeRunStatus.PENDING.value),
        _node_run("r", "b", NodeRunStatus.PENDING.value),
        _node_run("r", "output", NodeRunStatus.PENDING.value),
    ]
    # Only the Parallel node is ready (its predecessor Input is completed);
    # branch nodes wait until the Parallel completes.
    assert find_ready_nodes(graph, node_runs) == ["p"]
