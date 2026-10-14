"""FILE: vidbyte/tools/builtins/prebuilt/graphs.py

PURPOSE: Defines GraphsToolFunctions, the six prebuilt tools that work on graphs given as parallel lists of edge sources and targets: topological ordering, cycle finding, shortest paths by hops and by weight, connected components, and a critical-path schedule for tasks with durations.
ROLE IN CODEBASE: Re-exported by vidbyte/tools/builtins/prebuilt/__init__.py and wrapped in FunctionTool objects by PrebuiltTools in vidbyte/tools/toolsets/prebuilt.py when the GRAPHS category is chosen. Builds on PrebuiltToolSupport in _support.py for pairing the edge lists, the finite-float guard, and the argument error.
ARCHITECTURE NOTE: Every tool is a static method whose docstring's first paragraph is the model-facing description and whose parameters carry their own Field descriptions and caps, so FunctionTool builds the whole schema from the signature. Each tool first turns its edges into a node-to-sorted-successors map, and every algorithm is iterative and breaks ties by node name in code-point order, so no output depends on set or hash order. Weighted paths are summed exactly in Fraction from each weight's shortest text, so equal totals are true ties.
FUNCTION INVENTORY: topological_sort, find_graph_cycle, shortest_path, shortest_weighted_path, connected_components, and critical_path_schedule are the tools; _successors builds the adjacency map; _in_degrees, _heap_order, and _ready_levels implement Kahn's algorithm; _first_cycle runs the cycle search and _cycle_text writes a cycle for an error; _breadth_first_path finds a fewest-hop path; _weighted_links, _reversed_links, _distances_to, and _lowest_path implement the weighted search; _components groups connected nodes; _checked_tasks, _forward_pass, _backward_pass, and _critical_chain build the schedule; tool_functions lists the tools in catalogue order.
COMMON MODIFICATION PATTERNS: A new graph tool adds a static method with a 4 to 5 sentence description, its row in the spec's Appendix A.25, and its entry in tool_functions, and builds its adjacency with _successors so neighbor order stays sorted. A new tie-break rule changes the one helper that makes that choice.
WHAT NOT TO DO IN THIS FILE: 1. Do not iterate a set of node names to build an output; sort the names or follow an insertion-ordered dict. 2. Do not write a recursive search; graphs may hold ten thousand edges. 3. Do not compare float path totals for ties; sum the weights exactly instead.
KNOWN EDGE CASES: An edge from a node to itself is a cycle of two entries, and it makes topological_sort fail. shortest_path and shortest_weighted_path only know the nodes that appear in an edge. With zero-weight edges the weighted search still returns a simple path, because its depth-first search never revisits a node. A critical task's slack may be a tiny float residue below one billionth instead of exact zero.
RELATED DOCS: docs/spec/prebuilt-agent-tools/spec.md (Appendix A.25, section 9.2 items 2, 5, 13, and 14); vidbyte/tools/builtins/prebuilt/README.md
TESTS: tests/features/prebuilt_tools/test_prebuilt_rows_identifiers_lists_graphs.py and the catalogue-wide tests in tests/features/prebuilt_tools/
"""

from __future__ import annotations

import heapq
from collections import Counter, deque
from collections.abc import Mapping, Sequence
from fractions import Fraction
from typing import Annotated

from pydantic import Field

from vidbyte.lib.constants.prebuilt_tools import (
    PREBUILT_MAX_GRAPH_EDGES,
    PREBUILT_MAX_LIST_ITEMS,
    PREBUILT_MAX_NAME_CHARS,
    PREBUILT_MAX_SCHEDULE_TASKS,
)
from vidbyte.tools.builtins.prebuilt._support import (
    PrebuiltToolFunction,
    PrebuiltToolOutput,
    PrebuiltToolSupport,
)

_CRITICAL_SLACK_TOLERANCE = 1e-9

_NodeName = Annotated[str, Field(min_length=1, max_length=PREBUILT_MAX_NAME_CHARS)]

_SOURCES_PARAMETER_DESCRIPTION = "The node each edge starts from, one name per edge. Edge i runs from the i-th source to the i-th target, so this list pairs item by item with targets. Each name holds 1 to 200 characters and is compared exactly. The list may hold at most 10,000 edges."
_TARGETS_PARAMETER_DESCRIPTION = "The node each edge ends at, one name per edge, in the same order as sources. Its length must equal the length of sources, or the call fails naming targets. Each name holds 1 to 200 characters and is compared exactly. The list may hold at most 10,000 edges."
_NODES_PARAMETER_DESCRIPTION = "Extra node names to include even when no edge touches them. A name that already appears in an edge is not added twice. Each name holds 1 to 200 characters. The list may hold at most 10,000 names and defaults to empty."
_DIRECTED_PARAMETER_DESCRIPTION = "Whether each edge may only be followed from its source to its target. When false, every edge can be followed both ways. The default is true. Node names are matched exactly either way."
_START_PARAMETER_DESCRIPTION = "The name of the node where the path begins. It must be the source or target of at least one edge, or the call fails naming start. Names are compared exactly, including case. It holds 1 to 200 characters."
_GOAL_PARAMETER_DESCRIPTION = "The name of the node where the path ends. It must be the source or target of at least one edge, or the call fails naming goal. When it equals start, the path holds only that node. It holds 1 to 200 characters."


class GraphsToolFunctions:
    """The graphs category: ordering, cycles, paths, components, and critical-path schedules."""

    @staticmethod
    def topological_sort(
        sources: Annotated[list[_NodeName], Field(description=_SOURCES_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_GRAPH_EDGES)],
        targets: Annotated[list[_NodeName], Field(description=_TARGETS_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_GRAPH_EDGES)],
        nodes: Annotated[tuple[_NodeName, ...], Field(description=_NODES_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_LIST_ITEMS)] = (),
    ) -> PrebuiltToolOutput:
        """Order the nodes of a dependency graph so that every node comes after all of its prerequisites, and group them into levels that become ready together. Use it to plan build steps, task order, or course order from a list of dependencies. Edges run from a prerequisite to the node that depends on it, ties are broken by taking the smallest name in code-point order, and each level is sorted. A cycle, including an edge from a node to itself, fails with an error naming sources that lists one cycle."""
        # Pair the edge lists and map every node to its successors.
        edges = PrebuiltToolSupport.paired_values(sources, targets, "targets")
        successors = GraphsToolFunctions._successors(edges, nodes, True)
        in_degrees = GraphsToolFunctions._in_degrees(successors)

        # Order the nodes with a min-heap on names; nodes left out of
        # the order sit on or behind a cycle.
        order = GraphsToolFunctions._heap_order(successors, dict(in_degrees))
        if len(order) < len(successors):
            cycle = GraphsToolFunctions._first_cycle(successors)
            problem = f"the edges form a cycle ({GraphsToolFunctions._cycle_text(cycle)})"
            raise PrebuiltToolSupport.argument_error("sources", problem, "edges that form no cycle, including no edge from a node to itself")

        # Group the nodes by the round in which they become ready.
        return {"order": order, "levels": GraphsToolFunctions._ready_levels(successors, dict(in_degrees))}

    @staticmethod
    def find_graph_cycle(
        sources: Annotated[list[_NodeName], Field(description=_SOURCES_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_GRAPH_EDGES)],
        targets: Annotated[list[_NodeName], Field(description=_TARGETS_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_GRAPH_EDGES)],
        nodes: Annotated[tuple[_NodeName, ...], Field(description=_NODES_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_LIST_ITEMS)] = (),
    ) -> PrebuiltToolOutput:
        """Tell whether a directed graph has a cycle and show one cycle when it does. Use it to find circular dependencies before ordering tasks, modules, or steps. The search is depth-first from nodes in code-point order with successors visited in code-point order, and the first edge back to a node on the current path closes the cycle. The cycle is written closed, starting and ending at the same node, and it is empty when there is none. Edge lists of different lengths fail with an error naming targets."""
        edges = PrebuiltToolSupport.paired_values(sources, targets, "targets")
        cycle = GraphsToolFunctions._first_cycle(GraphsToolFunctions._successors(edges, nodes, True))
        return {"has_cycle": bool(cycle), "cycle": cycle}

    @staticmethod
    def shortest_path(
        sources: Annotated[list[_NodeName], Field(description=_SOURCES_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_GRAPH_EDGES)],
        targets: Annotated[list[_NodeName], Field(description=_TARGETS_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_GRAPH_EDGES)],
        start: Annotated[str, Field(description=_START_PARAMETER_DESCRIPTION, min_length=1, max_length=PREBUILT_MAX_NAME_CHARS)],
        goal: Annotated[str, Field(description=_GOAL_PARAMETER_DESCRIPTION, min_length=1, max_length=PREBUILT_MAX_NAME_CHARS)],
        directed: Annotated[bool, Field(description=_DIRECTED_PARAMETER_DESCRIPTION)] = True,
    ) -> PrebuiltToolOutput:
        """Find a path with the fewest edges between two nodes, with its number of hops. Use it to trace how one item connects to another in a dependency, link, or relationship graph. The search is breadth-first with neighbors visited in code-point order, and directed false lets every edge be followed both ways. An unreachable goal gives found false with an empty path, and a start or goal that is in no edge fails with an error naming it."""
        # Build the graph, then make sure both ends are in it.
        edges = PrebuiltToolSupport.paired_values(sources, targets, "targets")
        successors = GraphsToolFunctions._successors(edges, (), directed)
        for parameter_name, node in (("start", start), ("goal", goal)):
            if node not in successors:
                raise PrebuiltToolSupport.argument_error(parameter_name, "the node is not the source or target of any edge", "the name of a node that appears in sources or targets")

        # Search outward from the start one hop at a time.
        path = GraphsToolFunctions._breadth_first_path(successors, start, goal)
        return {"found": bool(path), "path": path, "hops": len(path) - 1 if path else None}

    @staticmethod
    def shortest_weighted_path(
        sources: Annotated[list[_NodeName], Field(description=_SOURCES_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_GRAPH_EDGES)],
        targets: Annotated[list[_NodeName], Field(description=_TARGETS_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_GRAPH_EDGES)],
        weights: Annotated[list[Annotated[float, Field(allow_inf_nan=False)]], Field(description="The weight of each edge, one finite number per edge in the same order as sources. Weights must be zero or more, and a negative weight fails naming weights. When several edges join the same two nodes, the lightest one is used. Its length must equal the number of edges.", max_length=PREBUILT_MAX_LIST_ITEMS)],
        start: Annotated[str, Field(description=_START_PARAMETER_DESCRIPTION, min_length=1, max_length=PREBUILT_MAX_NAME_CHARS)],
        goal: Annotated[str, Field(description=_GOAL_PARAMETER_DESCRIPTION, min_length=1, max_length=PREBUILT_MAX_NAME_CHARS)],
        directed: Annotated[bool, Field(description=_DIRECTED_PARAMETER_DESCRIPTION)] = True,
    ) -> PrebuiltToolOutput:
        """Find the path with the lowest total weight between two nodes, with that total. Use it for routes, costs, or delays where the edges have different weights. It runs Dijkstra's algorithm on exact sums, uses the lightest of any parallel edges, and breaks ties between equal totals by the path that is smaller in code-point order. An unreachable goal gives found false, and a negative weight, a weight count that differs from the edge count, or an unknown start or goal fails with an error naming that parameter."""
        # Pair edges with weights and keep the lightest parallel edge.
        edges = PrebuiltToolSupport.paired_values(sources, targets, "targets")
        forward = GraphsToolFunctions._weighted_links(PrebuiltToolSupport.paired_values(edges, weights, "weights"), directed)
        for parameter_name, node in (("start", start), ("goal", goal)):
            if node not in forward:
                raise PrebuiltToolSupport.argument_error(parameter_name, "the node is not the source or target of any edge", "the name of a node that appears in sources or targets")

        # Measure every node's exact distance to the goal; a start
        # with no distance cannot reach it.
        distances = GraphsToolFunctions._distances_to(GraphsToolFunctions._reversed_links(forward), goal)
        if start not in distances:
            return {"found": False, "path": [], "total_weight": None}

        # Search from the start along edges that keep the total lowest,
        # trying smaller names first, so the first path to reach the
        # goal is the smallest of the lowest-total paths.
        path = GraphsToolFunctions._lowest_path(forward, distances, start, goal)

        # Report the exact total as a float, refusing an overflow.
        try:
            total = float(distances[start])
        except OverflowError as exc:
            raise PrebuiltToolSupport.argument_error("weights", "the path total is outside the floating-point range", "weights whose path total is a finite number") from exc
        return {"found": True, "path": path, "total_weight": total}

    @staticmethod
    def connected_components(
        sources: Annotated[list[_NodeName], Field(description=_SOURCES_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_GRAPH_EDGES)],
        targets: Annotated[list[_NodeName], Field(description=_TARGETS_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_GRAPH_EDGES)],
        nodes: Annotated[tuple[_NodeName, ...], Field(description=_NODES_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_LIST_ITEMS)] = (),
    ) -> PrebuiltToolOutput:
        """Group the nodes of a graph into connected components, ignoring the direction of edges. Use it to find clusters, separate subsystems, or isolated items in a set of links. Each component is sorted in code-point order, and components are ordered by size, largest first, then by their first node. Extra nodes with no edges form components of their own, and edge lists of different lengths fail with an error naming targets."""
        edges = PrebuiltToolSupport.paired_values(sources, targets, "targets")
        components = GraphsToolFunctions._components(GraphsToolFunctions._successors(edges, nodes, False))
        return {"components": components, "count": len(components)}

    @staticmethod
    def critical_path_schedule(
        tasks: Annotated[list[_NodeName], Field(description="The names of the tasks in the project, each listed once. The order does not matter, because the schedule follows the dependencies. A repeated name fails with an error naming tasks. The list must hold between 1 and 1,000 names of 1 to 200 characters each.", min_length=1, max_length=PREBUILT_MAX_SCHEDULE_TASKS)],
        durations: Annotated[list[Annotated[float, Field(allow_inf_nan=False)]], Field(description="The duration of each task, one finite number per task in the same order as tasks. Durations must be zero or more and share one time unit. A negative duration or a count that differs from tasks fails with an error naming durations. The list may hold at most 10,000 numbers.", max_length=PREBUILT_MAX_LIST_ITEMS)],
        dependency_sources: Annotated[tuple[_NodeName, ...], Field(description="The task that must finish first in each dependency. Dependency i runs from the i-th source to the i-th target. Every name must be one of the tasks. A cycle among the dependencies fails with an error naming this parameter. The list may hold at most 10,000 names and defaults to empty.", max_length=PREBUILT_MAX_GRAPH_EDGES)] = (),
        dependency_targets: Annotated[tuple[_NodeName, ...], Field(description="The task that waits for its source in each dependency, in the same order as dependency_sources. Its length must equal the length of dependency_sources. A name that is not one of the tasks, in either list, fails with an error naming this parameter. The list may hold at most 10,000 names and defaults to empty.", max_length=PREBUILT_MAX_GRAPH_EDGES)] = (),
    ) -> PrebuiltToolOutput:
        """Compute the critical path, the total duration, and the earliest and latest start and finish and the slack of every task in a project with dependencies. Use it to find which tasks would delay the whole project if they slipped and how much room the other tasks have. A dependency means its source must finish before its target starts, the schedule follows topological order with ties broken by name, and a task is critical when its slack is at most one billionth. A duplicate task, a bad duration, an unknown task in a dependency, mismatched lists, or a cycle fails with an error naming the parameter at fault."""
        # Check the task list, the durations, and the dependencies.
        duration_of, dependencies = GraphsToolFunctions._checked_tasks(tasks, durations, dependency_sources, dependency_targets)

        # Order the tasks so each comes after the tasks it waits for.
        successors = GraphsToolFunctions._successors(dependencies, tasks, True)
        in_degrees = GraphsToolFunctions._in_degrees(successors)
        order = GraphsToolFunctions._heap_order(successors, dict(in_degrees))
        if len(order) < len(successors):
            problem = f"the dependencies form a cycle ({GraphsToolFunctions._cycle_text(GraphsToolFunctions._first_cycle(successors))})"
            raise PrebuiltToolSupport.argument_error("dependency_sources", problem, "dependencies that form no cycle")

        # Push earliest starts forward, then latest starts backward
        # from the project's finish.
        earliest = GraphsToolFunctions._forward_pass(order, successors, duration_of)
        project = PrebuiltToolSupport.float_result(max(earliest[task] + duration_of[task] for task in order), "durations")
        latest = GraphsToolFunctions._backward_pass(order, successors, duration_of, project)

        # Write one row per task and follow the critical tasks through.
        schedule = [
            {
                "task": task,
                "earliest_start": earliest[task],
                "earliest_finish": earliest[task] + duration_of[task],
                "latest_start": latest[task],
                "latest_finish": latest[task] + duration_of[task],
                "slack": latest[task] - earliest[task],
                "critical": latest[task] - earliest[task] <= _CRITICAL_SLACK_TOLERANCE,
            }
            for task in order
        ]
        critical_path = GraphsToolFunctions._critical_chain(order, successors, in_degrees, earliest, latest, duration_of)
        return {"project_duration": project, "critical_path": critical_path, "schedule": schedule}

    @staticmethod
    def _successors(edges: Sequence[tuple[str, str]], extra_nodes: Sequence[str], directed: bool) -> dict[str, list[str]]:
        """Map every node, in first-seen order, to its distinct successors in code-point order; undirected edges count both ways."""
        linked: dict[str, dict[str, None]] = {}
        for source, target in edges:
            linked.setdefault(source, {})[target] = None
            linked.setdefault(target, {})
            if not directed:
                linked[target][source] = None
        for node in extra_nodes:
            linked.setdefault(node, {})
        return {node: sorted(neighbors) for node, neighbors in linked.items()}

    @staticmethod
    def _in_degrees(successors: Mapping[str, Sequence[str]]) -> dict[str, int]:
        """Count the distinct edges that enter each node."""
        entering = Counter(node for neighbors in successors.values() for node in neighbors)
        return {node: entering[node] for node in successors}

    @staticmethod
    def _heap_order(successors: Mapping[str, Sequence[str]], in_degrees: dict[str, int]) -> list[str]:
        """Run Kahn's algorithm with a min-heap on names, consuming in_degrees; nodes on or behind a cycle are left out."""
        ready = sorted(node for node, count in in_degrees.items() if count == 0)
        order: list[str] = []
        while ready:
            node = heapq.heappop(ready)
            order.append(node)
            for successor in successors[node]:
                in_degrees[successor] -= 1
                if in_degrees[successor] == 0:
                    heapq.heappush(ready, successor)
        return order

    @staticmethod
    def _ready_levels(successors: Mapping[str, Sequence[str]], in_degrees: dict[str, int]) -> list[list[str]]:
        """Group nodes by the round of Kahn's algorithm in which they become ready, each group sorted, consuming in_degrees."""
        level = sorted(node for node, count in in_degrees.items() if count == 0)
        levels: list[list[str]] = []
        while level:
            levels.append(level)
            following: list[str] = []
            for successor in (successor for node in level for successor in successors[node]):
                in_degrees[successor] -= 1
                if in_degrees[successor] == 0:
                    following.append(successor)
            level = sorted(following)
        return levels

    @staticmethod
    def _first_cycle(successors: Mapping[str, Sequence[str]]) -> list[str]:
        """Find the first cycle a depth-first search meets, written closed, or return an empty list when there is none."""
        # A node is 1 while it is on the current path and 2 once every
        # node after it has been searched.
        state: dict[str, int] = {}
        for root in sorted(successors):
            if root in state:
                continue
            path, cursors = [root], [iter(successors[root])]
            state[root] = 1
            while cursors:
                successor = next(cursors[-1], None)
                if successor is None:
                    state[path.pop()] = 2
                    cursors.pop()
                elif state.get(successor) == 1:
                    return path[path.index(successor) :] + [successor]
                elif successor not in state:
                    state[successor] = 1
                    path.append(successor)
                    cursors.append(iter(successors[successor]))
        return []

    @staticmethod
    def _cycle_text(cycle: Sequence[str]) -> str:
        """Write a cycle for an error message, shortening long names and long cycles so no argument is echoed at length."""
        shown = PrebuiltToolSupport.shortened_names(cycle)
        hidden = len(cycle) - len(shown)
        text = " -> ".join(shown)
        return text if hidden == 0 else f"{text} and {hidden} more"

    @staticmethod
    def _breadth_first_path(successors: Mapping[str, Sequence[str]], start: str, goal: str) -> list[str]:
        """Return the first fewest-hop path found by a breadth-first search over sorted neighbors, or an empty list."""
        parents: dict[str, str | None] = {start: None}
        pending = deque([start])
        while pending and goal not in parents:
            node = pending.popleft()
            for successor in successors[node]:
                if successor not in parents:
                    parents[successor] = node
                    pending.append(successor)
        if goal not in parents:
            return []
        path = [goal]
        while (parent := parents[path[-1]]) is not None:
            path.append(parent)
        return path[::-1]

    @staticmethod
    def _weighted_links(weighted_edges: Sequence[tuple[tuple[str, str], float]], directed: bool) -> dict[str, dict[str, Fraction]]:
        """Map each node to its successors and the exact weight of the lightest edge to each, refusing a negative weight."""
        forward: dict[str, dict[str, Fraction]] = {}
        for index, ((source, target), weight) in enumerate(weighted_edges):
            if weight < 0:
                raise PrebuiltToolSupport.argument_error("weights", f"the weight at index {index} is negative", "weights of zero or more, one for each edge")
            exact = Fraction(repr(weight))
            arcs = ((source, target),) if directed else ((source, target), (target, source))
            for tail, head in arcs:
                heads = forward.setdefault(tail, {})
                forward.setdefault(head, {})
                heads[head] = min(heads.get(head, exact), exact)
        return forward

    @staticmethod
    def _reversed_links(forward: Mapping[str, Mapping[str, Fraction]]) -> dict[str, dict[str, Fraction]]:
        """Turn every weighted edge around, so a search can run backward from the goal."""
        backward: dict[str, dict[str, Fraction]] = {node: {} for node in forward}
        for tail, heads in forward.items():
            for head, weight in heads.items():
                backward[head][tail] = weight
        return backward

    @staticmethod
    def _distances_to(backward: Mapping[str, Mapping[str, Fraction]], goal: str) -> dict[str, Fraction]:
        """Run Dijkstra's algorithm backward from the goal and return each node's exact distance to it."""
        distances: dict[str, Fraction] = {}
        pending: list[tuple[Fraction, str]] = [(Fraction(0), goal)]
        while pending:
            distance, node = heapq.heappop(pending)
            if node in distances:
                continue
            distances[node] = distance
            for previous, weight in backward[node].items():
                if previous not in distances:
                    heapq.heappush(pending, (distance + weight, previous))
        return distances

    @staticmethod
    def _lowest_path(forward: Mapping[str, Mapping[str, Fraction]], distances: Mapping[str, Fraction], start: str, goal: str) -> list[str]:
        """Return the smallest simple path in code-point order among the lowest-total paths from start to goal."""
        # A depth-first search over edges on a lowest-total path tries
        # successors in code-point order. A node it leaves without
        # reaching the goal cannot reach it without passing through the
        # current path, so skipping that node later loses nothing.
        path, cursors, visited = [start], [iter(sorted(forward[start]))], {start}
        while cursors and path[-1] != goal:
            head = next(cursors[-1], None)
            if head is None:
                path.pop()
                cursors.pop()
            elif head not in visited and head in distances and forward[path[-1]][head] + distances[head] == distances[path[-1]]:
                visited.add(head)
                path.append(head)
                cursors.append(iter(sorted(forward[head])))
        return path

    @staticmethod
    def _components(successors: Mapping[str, Sequence[str]]) -> list[list[str]]:
        """Group nodes connected by undirected edges, sort each group, and order groups by size and then by first node."""
        seen: set[str] = set()
        components: list[list[str]] = []
        for root in sorted(successors):
            if root in seen:
                continue
            seen.add(root)
            members, pending = [root], [root]
            while pending:
                fresh = [neighbor for neighbor in successors[pending.pop()] if neighbor not in seen]
                seen.update(fresh)
                pending.extend(fresh)
                members.extend(fresh)
            components.append(sorted(members))
        return sorted(components, key=lambda component: (-len(component), component[0]))

    @staticmethod
    def _checked_tasks(tasks: Sequence[str], durations: Sequence[float], dependency_sources: Sequence[str], dependency_targets: Sequence[str]) -> tuple[dict[str, float], list[tuple[str, str]]]:
        """Check the task names, durations, and dependencies, and return each task's duration with the dependency pairs."""
        # Refuse a repeated task, then pair each task with its duration.
        duration_of: dict[str, float] = {}
        for index, task in enumerate(tasks):
            if task in duration_of:
                raise PrebuiltToolSupport.argument_error("tasks", f"the task at index {index} repeats an earlier name", "task names that are all different")
            duration_of[task] = 0.0
        for index, (task, duration) in enumerate(PrebuiltToolSupport.paired_values(tasks, durations, "durations")):
            if duration < 0:
                raise PrebuiltToolSupport.argument_error("durations", f"the duration at index {index} is negative", "durations of zero or more, one for each task")
            duration_of[task] = duration

        # Pair the dependency lists and refuse a name outside the tasks.
        dependencies = PrebuiltToolSupport.paired_values(dependency_sources, dependency_targets, "dependency_targets")
        for index, (source, target) in enumerate(dependencies):
            if source not in duration_of or target not in duration_of:
                raise PrebuiltToolSupport.argument_error("dependency_targets", f"dependency {index} names a task that is not in tasks", "dependencies between tasks that appear in tasks")
        return duration_of, dependencies

    @staticmethod
    def _forward_pass(order: Sequence[str], successors: Mapping[str, Sequence[str]], duration_of: Mapping[str, float]) -> dict[str, float]:
        """Compute each task's earliest start: the latest earliest finish among the tasks it waits for, or zero."""
        earliest = dict.fromkeys(order, 0.0)
        for task in order:
            finish = earliest[task] + duration_of[task]
            for successor in successors[task]:
                earliest[successor] = max(earliest[successor], finish)
        return earliest

    @staticmethod
    def _backward_pass(order: Sequence[str], successors: Mapping[str, Sequence[str]], duration_of: Mapping[str, float], project: float) -> dict[str, float]:
        """Compute each task's latest start: its latest finish, the earliest latest start among its successors, minus its duration."""
        latest: dict[str, float] = {}
        for task in reversed(order):
            finish = min((latest[successor] for successor in successors[task]), default=project)
            latest[task] = finish - duration_of[task]
        return latest

    @staticmethod
    def _critical_chain(order: Sequence[str], successors: Mapping[str, Sequence[str]], in_degrees: Mapping[str, int], earliest: Mapping[str, float], latest: Mapping[str, float], duration_of: Mapping[str, float]) -> list[str]:
        """Follow critical tasks from the smallest-named critical start task, taking the smallest critical successor that starts as it finishes."""
        critical = {task for task in order if latest[task] - earliest[task] <= _CRITICAL_SLACK_TOLERANCE}
        starts = [task for task in sorted(critical) if in_degrees[task] == 0]
        chain = starts[:1]
        while chain:
            finish = earliest[chain[-1]] + duration_of[chain[-1]]
            following = next((task for task in successors[chain[-1]] if task in critical and abs(earliest[task] - finish) <= _CRITICAL_SLACK_TOLERANCE), None)
            if following is None:
                break
            chain.append(following)
        return chain

    @classmethod
    def tool_functions(cls) -> tuple[PrebuiltToolFunction, ...]:
        """Return the category's tool functions in catalogue order."""
        return (
            cls.topological_sort,
            cls.find_graph_cycle,
            cls.shortest_path,
            cls.shortest_weighted_path,
            cls.connected_components,
            cls.critical_path_schedule,
        )


__all__ = ["GraphsToolFunctions"]
