"""graph.py — dependency graph helpers (pure, no IO)."""
from __future__ import annotations

import os
import sys
_d = os.path.dirname(os.path.abspath(__file__))
if _d not in sys.path:
    sys.path.insert(0, _d)
from storage import detect_cycle


def validate_edges(edges):
    """edges: {job_id: depends_on_or_None}. Returns (ok, message)."""
    norm = {k: ([v] if v else []) for k, v in edges.items()}
    # unknown dep check
    for node, deps in norm.items():
        for d in deps:
            if d not in norm:
                return False, f"Unknown dependency {d!r} for job {node!r}"
    cycle = detect_cycle(norm)
    if cycle:
        return False, "Dependency cycle detected: " + " -> ".join(cycle)
    return True, "ok"


def topo_order(edges):
    """Kahn's algorithm, deterministic. Assumes validated DAG."""
    norm = {k: ([v] if v else []) for k, v in edges.items()}
    order = []
    remaining = dict(norm)
    while remaining:
        ready = sorted([n for n, deps in remaining.items() if all(d not in remaining for d in deps)])
        if not ready:
            break  # cycle — caller should have validated
        n = ready[0]
        order.append(n)
        del remaining[n]
    return order
