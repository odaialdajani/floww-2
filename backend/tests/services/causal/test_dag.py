"""
backend/tests/services/causal/test_dag.py

Unit tests for causal/dag.py — Causal DAG.

Coverage:
    - DAG initialization
    - Parent/child relationships
    - Ancestor/descendant computation
    - Acyclicity check
    - D-separation
    - Backdoor paths
    - Adjustment set
    - Mermaid output
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))


class TestCausalDAG:
    def test_init_default(self):
        from services.causal.dag import CausalDAG
        dag = CausalDAG()
        assert len(dag.nodes) == 8
        assert len(dag.edges) > 0

    def test_init_custom(self):
        from services.causal.dag import CausalDAG
        dag = CausalDAG(nodes=["a", "b", "c"], edges=[("a", "b"), ("b", "c")])
        assert dag.nodes == ["a", "b", "c"]
        assert dag.get_parents("b") == ["a"]
        assert dag.get_children("a") == ["b"]

    def test_get_parents(self):
        from services.causal.dag import CausalDAG
        dag = CausalDAG()
        parents = dag.get_parents("gex")
        assert "spot" in parents

    def test_get_children(self):
        from services.causal.dag import CausalDAG
        dag = CausalDAG()
        children = dag.get_children("spot")
        assert "gex" in children

    def test_get_ancestors(self):
        from services.causal.dag import CausalDAG
        dag = CausalDAG()
        ancestors = dag.get_ancestors("kyle_lambda")
        # vpin -> kyle_lambda, qi -> kyle_lambda
        assert "vpin" in ancestors or "qi" in ancestors

    def test_get_descendants(self):
        from services.causal.dag import CausalDAG
        dag = CausalDAG()
        descendants = dag.get_descendants("spot")
        assert "gex" in descendants

    def test_acyclic_check(self):
        from services.causal.dag import CausalDAG
        dag = CausalDAG()
        is_acyclic, msg = dag.check_acyclic()
        assert is_acyclic is True, f"DAG should be acyclic: {msg}"

    def test_acyclic_detects_cycle(self):
        from services.causal.dag import CausalDAG
        # Create a cycle: a -> b -> c -> a
        dag = CausalDAG(
            nodes=["a", "b", "c"],
            edges=[("a", "b"), ("b", "c"), ("c", "a")],
        )
        is_acyclic, msg = dag.check_acyclic()
        assert is_acyclic is False

    def test_d_separation(self):
        from services.causal.dag import CausalDAG
        dag = CausalDAG(
            nodes=["a", "b", "c"],
            edges=[("a", "b"), ("b", "c")],
        )
        # a and c are NOT d-separated (path a -> b -> c)
        assert dag.is_d_separated("a", "c", set()) is False
        # a and c ARE d-separated given b
        assert dag.is_d_separated("a", "c", {"b"}) is True

    def test_d_separation_collider(self):
        from services.causal.dag import CausalDAG
        # Collider: a -> b <- c
        dag = CausalDAG(
            nodes=["a", "b", "c"],
            edges=[("a", "b"), ("c", "b")],
        )
        # a and c are d-separated (collider blocks path)
        assert dag.is_d_separated("a", "c", set()) is True
        # a and c are NOT d-separated given b (conditioning on collider opens path)
        assert dag.is_d_separated("a", "c", {"b"}) is False

    def test_backdoor_paths(self):
        from services.causal.dag import CausalDAG
        # Confounder: z -> x, z -> y
        dag = CausalDAG(
            nodes=["z", "x", "y"],
            edges=[("z", "x"), ("z", "y"), ("x", "y")],
        )
        paths = dag.get_backdoor_paths("x", "y")
        assert len(paths) > 0

    def test_adjustment_set(self):
        from services.causal.dag import CausalDAG
        dag = CausalDAG(
            nodes=["z", "x", "y"],
            edges=[("z", "x"), ("z", "y"), ("x", "y")],
        )
        adj = dag.get_adjustment_set("x", "y")
        assert "z" in adj

    def test_mermaid_output(self):
        from services.causal.dag import CausalDAG
        dag = CausalDAG()
        mermaid = dag.to_mermaid()
        assert "graph TD" in mermaid
        assert "-->" in mermaid

    def test_get_state(self):
        from services.causal.dag import CausalDAG
        dag = CausalDAG()
        state = dag.get_state()
        assert "nodes" in state
        assert "edges" in state
        assert state["n_nodes"] == 8

    def test_dag_specific_edges(self):
        """Verify the dealer-hedging DAG has expected edges."""
        from services.causal.dag import CausalDAG
        dag = CausalDAG()
        # spot -> GEX (mechanical)
        assert ("spot", "gex") in dag.edges
        # GEX -> dealer_hedge_pressure (theoretical)
        assert ("gex", "dealer_hedge_pressure") in dag.edges
        # VPIN -> kyle_lambda
        assert ("vpin", "kyle_lambda") in dag.edges

    def test_empty_dag(self):
        from services.causal.dag import CausalDAG
        dag = CausalDAG(nodes=["a"], edges=[])
        assert dag.get_parents("a") == []
        assert dag.get_children("a") == []
        is_acyclic, _ = dag.check_acyclic()
        assert is_acyclic is True
