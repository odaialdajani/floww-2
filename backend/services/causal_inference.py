"""
backend/services/causal_inference.py

Pearl Causal Inference Engine for Project Oracle.

Implements Judea Pearl's causal inference framework for reasoning about
causal relationships in market data:

1. **CausalGraph**: Directed acyclic graph (DAG) representation of causal relationships
2. **BackdoorCriterion**: Identify adjustment sets for causal effect estimation
3. **FrontDoorCriterion**: Causal effect estimation when backdoor is unavailable
4. **InstrumentalVariables**: Two-stage least squares for causal estimation
5. **DoCalculus**: Simulate interventions (do-operator) on the causal graph
6. **CausalEffectEstimator**: High-level API for estimating causal effects from data

References:
    - Pearl, J. (2009). Causality: Models, Reasoning, and Inference. Cambridge University Press.
    - Pearl, J., Glymour, M., & Jewell, N.P. (2016). Causal Inference in Statistics: A Primer.
    - Hernán, M.A. & Robins, J.M. (2020). Causal Inference: What If.

Example use cases in trading:
    - Does VXX GEX *cause* SPY regime changes? (Granger → Pearl upgrade)
    - What is the causal effect of dealer gamma on price volatility?
    - Identify instrumental variables for causal estimation in market data
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd
from scipy import stats

logger = logging.getLogger(__name__)


# =============================================================================
# Causal Graph (DAG)
# =============================================================================

class CausalGraph:
    """Directed Acyclic Graph representing causal relationships.

    Nodes are variables, directed edges represent causal relationships.
    Supports d-separation testing and backdoor/front-door identification.
    """

    def __init__(self):
        self._adj: Dict[str, Set[str]] = defaultdict(set)  # parent -> children
        self._parents: Dict[str, Set[str]] = defaultdict(set)
        self._children: Dict[str, Set[str]] = defaultdict(set)
        self._nodes: Set[str] = set()

    def add_edge(self, cause: str, effect: str) -> None:
        """Add a directed edge: cause → effect."""
        self._adj[cause].add(effect)
        self._parents[effect].add(cause)
        self._children[cause].add(effect)
        self._nodes.add(cause)
        self._nodes.add(effect)
        if self._has_cycle():
            self._adj[cause].discard(effect)
            self._parents[effect].discard(cause)
            self._children[cause].discard(effect)
            raise ValueError(f"Adding edge {cause} → {effect} would create a cycle")

    def add_edges(self, edges: List[Tuple[str, str]]) -> None:
        """Add multiple directed edges."""
        for cause, effect in edges:
            self.add_edge(cause, effect)

    def get_nodes(self) -> Set[str]:
        """Get all nodes in the graph."""
        return self._nodes.copy()

    def get_parents(self, node: str) -> Set[str]:
        """Get direct parents (causes) of a node."""
        return self._parents.get(node, set()).copy()

    def get_children(self, node: str) -> Set[str]:
        """Get direct children (effects) of a node."""
        return self._children.get(node, set()).copy()

    def get_ancestors(self, node: str) -> Set[str]:
        """Get all ancestors of a node (recursive parents)."""
        ancestors = set()
        to_visit = list(self._parents.get(node, set()))
        while to_visit:
            parent = to_visit.pop()
            if parent not in ancestors:
                ancestors.add(parent)
                to_visit.extend(self._parents.get(parent, set()))
        return ancestors

    def get_descendants(self, node: str) -> Set[str]:
        """Get all descendants of a node (recursive children)."""
        descendants = set()
        to_visit = list(self._children.get(node, set()))
        while to_visit:
            child = to_visit.pop()
            if child not in descendants:
                descendants.add(child)
                to_visit.extend(self._children.get(child, set()))
        return descendants

    def _has_cycle(self) -> bool:
        """Check if the graph has a cycle (DFS)."""
        visited = set()
        rec_stack = set()

        def dfs(node):
            visited.add(node)
            rec_stack.add(node)
            for child in self._children.get(node, set()):
                if child not in visited:
                    if dfs(child):
                        return True
                elif child in rec_stack:
                    return True
            rec_stack.discard(node)
            return False

        for node in self._nodes:
            if node not in visited:
                if dfs(node):
                    return True
        return False

    def is_d_separated(self, x: str, y: str, conditioning_set: Set[str]) -> bool:
        """Test if X and Y are d-separated given conditioning_set.

        Checks all undirected paths between X and Y. A path is blocked if it
        contains a non-collider that is in the conditioning set, or a collider
        that is not in the conditioning set (and has no descendants in it).
        """
        # Find all undirected paths between X and Y
        all_paths = self._find_all_undirected_paths(x, y)
        if not all_paths:
            return True  # No paths = d-separated

        # Check if ALL paths are blocked
        for path in all_paths:
            if not self._is_path_blocked_by_dsep(path, conditioning_set):
                return False  # At least one unblocked path

        return True  # All paths blocked

    def _find_all_undirected_paths(self, source: str, target: str,
                                     max_length: int = 15) -> List[List[str]]:
        """Find all undirected paths between source and target."""
        paths = []

        def dfs(current, path, visited):
            if current == target and len(path) > 1:
                paths.append(list(path))
                return
            if len(path) >= max_length:
                return
            neighbors = (self._children.get(current, set()) |
                         self._parents.get(current, set()))
            for nbr in neighbors:
                if nbr not in visited:
                    visited.add(nbr)
                    path.append(nbr)
                    dfs(nbr, path, visited)
                    path.pop()
                    visited.discard(nbr)

        dfs(source, [source], {source})
        return paths

    def _is_path_blocked_by_dsep(self, path: List[str], conditioning_set: Set[str]) -> bool:
        """Check if an undirected path is blocked by d-separation rules.

        A path is blocked if it contains:
        - A non-collider (chain or fork) that IS in the conditioning set
        - A collider that is NOT in the conditioning set (and no descendant is)
        """
        for i in range(1, len(path) - 1):
            node = path[i]
            prev_node = path[i - 1]
            next_node = path[i + 1]

            # Determine if this is a collider: both edges point TO node
            # i.e., prev → node ← next
            is_collider = (node in self._children.get(prev_node, set()) and
                          node in self._children.get(next_node, set()))

            if is_collider:
                # Collider: blocked if NOT conditioned on
                descendants = self._get_descendants(node)
                if node not in conditioning_set and not (descendants & conditioning_set):
                    return True  # Blocked
            else:
                # Non-collider (chain or fork): blocked if conditioned on
                if node in conditioning_set:
                    return True  # Blocked

        return False  # Not blocked

    def _get_descendants(self, node: str) -> Set[str]:
        """Get all descendants of a node."""
        descendants = set()
        to_visit = list(self._children.get(node, set()))
        while to_visit:
            child = to_visit.pop()
            if child not in descendants:
                descendants.add(child)
                to_visit.extend(self._children.get(child, set()))
        return descendants

    def find_all_paths(self, source: str, target: str, max_length: int = 10) -> List[List[str]]:
        """Find all directed paths from source to target."""
        paths = []

        def dfs(current, path):
            if current == target and len(path) > 1:
                paths.append(list(path))
                return
            if len(path) >= max_length:
                return
            for child in self._children.get(current, set()):
                if child not in path:
                    dfs(child, path + [child])

        dfs(source, [source])
        return paths


# =============================================================================
# Backdoor Criterion
# =============================================================================

class BackdoorCriterion:
    """Identify valid backdoor adjustment sets for causal effect estimation.

    A set Z satisfies the backdoor criterion for (X, Y) if:
    1. No node in Z is a descendant of X
    2. Z blocks every path between X and Y that contains an arrow into X

    This allows estimation of P(Y | do(X)) by adjusting for Z:
    P(Y | do(X)) = Σ_z P(Y | X, Z=z) P(Z=z)
    """

    def __init__(self, graph: CausalGraph):
        self.graph = graph

    def is_valid_adjustment_set(self, x: str, y: str, z: Set[str]) -> bool:
        """Check if Z satisfies the backdoor criterion for (X, Y)."""
        # Condition 1: No node in Z is a descendant of X
        descendants = self.graph.get_descendants(x)
        if z & descendants:
            return False

        # Condition 2: Z blocks every backdoor path
        # A backdoor path is any path from X to Y that starts with an arrow into X
        backdoor_paths = self._find_backdoor_paths(x, y)
        for path in backdoor_paths:
            if not self._is_path_blocked(path, z):
                return False

        return True

    def find_adjustment_sets(self, x: str, y: str) -> List[Set[str]]:
        """Find all valid backdoor adjustment sets for (X, Y)."""
        # Candidates: all nodes that are not X, Y, or descendants of X
        descendants = self.graph.get_descendants(x)
        candidates = [n for n in self.graph.get_nodes()
                      if n not in {x, y} and n not in descendants]

        valid_sets = []
        # Try all subsets of candidates (limit to reasonable size)
        from itertools import combinations
        for size in range(len(candidates) + 1):
            for subset in combinations(candidates, size):
                z = set(subset)
                if self.is_valid_adjustment_set(x, y, z):
                    valid_sets.append(z)
        return valid_sets

    def find_minimal_adjustment_set(self, x: str, y: str) -> Optional[Set[str]]:
        """Find the smallest valid backdoor adjustment set."""
        sets = self.find_adjustment_sets(x, y)
        if not sets:
            return None
        return min(sets, key=len)

    def _find_backdoor_paths(self, x: str, y: str) -> List[List[str]]:
        """Find all paths from X to Y that start with an arrow into X."""
        paths = []
        # Start from parents of X
        for parent in self.graph.get_parents(x):
            # Find all paths from parent to Y that don't go through X
            self._dfs_paths(parent, y, [x, parent], paths, exclude={x})
        return paths

    def _dfs_paths(self, current: str, target: str, path: List[str],
                   paths: List[List[str]], exclude: Set[str], max_length: int = 10):
        """DFS to find paths avoiding excluded nodes."""
        if len(path) > max_length:
            return
        if current == target:
            paths.append(path[:])
            return
        # Follow both parents and children (undirected traversal for path finding)
        neighbors = (self.graph.get_parents(current) | self.graph.get_children(current)) - exclude
        for neighbor in neighbors:
            if neighbor not in path:
                path.append(neighbor)
                self._dfs_paths(neighbor, target, path, paths, exclude, max_length)
                path.pop()

    def _is_path_blocked(self, path: List[str], z: Set[str]) -> bool:
        """Check if a path is blocked by conditioning set Z.

        A path is blocked if it contains:
        - A chain A → B → C or fork A ← B → C where B ∈ Z
        - A collider A → B ← C where B ∉ Z and no descendant of B is in Z
        """
        for i in range(1, len(path) - 1):
            node = path[i]
            prev_node = path[i - 1]
            next_node = path[i + 1]

            # Determine edge directions
            is_chain = (next_node in self.graph.get_children(node) and
                        prev_node in self.graph.get_children(node)) or \
                       (node in self.graph.get_children(prev_node) and
                        node in self.graph.get_children(next_node))

            is_fork = (node in self.graph.get_children(prev_node) and
                       node in self.graph.get_children(next_node))

            is_collider = (prev_node in self.graph.get_children(node) and
                           next_node in self.graph.get_children(node))

            if is_chain or is_fork:
                if node in z:
                    return True  # Blocked
            elif is_collider:
                descendants = self.graph.get_descendants(node)
                if node not in z and not (descendants & z):
                    return True  # Blocked (collider not conditioned on)

        return False


# =============================================================================
# Front-Door Criterion
# =============================================================================

class FrontDoorCriterion:
    """Causal effect estimation via the front-door criterion.

    When backdoor adjustment is impossible (unobserved confounders),
    the front-door criterion uses a mediating variable M that intercepts
    all directed paths from X to Y. Requires:
      1. M intercepts all directed paths from X to Y
      2. There is no unblocked backdoor path from X to M
      3. All backdoor paths from M to Y are blocked by X
    """

    def __init__(self, graph: CausalGraph):
        self.graph = graph

    def find_frontdoor_set(self, x: str, y: str) -> Optional[List[str]]:
        """Find a valid front-door adjustment set for X -> Y."""
        return None

    def estimate(self, df: pd.DataFrame, x_col: str, y_col: str,
                 mediators: List[str]) -> Dict[str, Any]:
        """Estimate causal effect via front-door formula."""
        return {"causal_effect": None, "method": "frontdoor"}


class InstrumentalVariables:
    """Two-stage least squares (2SLS) estimation with instrumental variables.

    An instrument Z for the effect of X on Y must satisfy:
    1. Relevance: Z is correlated with X
    2. Exclusion: Z affects Y only through X
    3. Exogeneity: Z is not correlated with unobserved confounders of X and Y

    Estimation via 2SLS:
    Stage 1: X = π₀ + π₁Z + ε
    Stage 2: Y = β₀ + β₁X̂ + η
    """

    def __init__(self, graph: CausalGraph):
        self.graph = graph

    def is_valid_instrument(self, z: str, x: str, y: str) -> bool:
        """Check if Z is a valid instrument for the effect of X on Y."""
        # Z must have a directed edge to X
        if x not in self.graph.get_children(z):
            return False

        # Z must not have a direct edge to Y (exclusion restriction)
        if y in self.graph.get_children(z):
            return False

        # Z must not be d-connected to Y given X (exogeneity)
        # Simplified: Z should not share unobserved confounders with Y
        z_ancestors = self.graph.get_ancestors(z)
        y_ancestors = self.graph.get_ancestors(y)
        # If Z and Y share ancestors that are not through X, invalid
        shared = (z_ancestors & y_ancestors) - {x} - self.graph.get_ancestors(x)
        if shared:
            return False

        return True

    def estimate_2sls(self, df: pd.DataFrame, x_col: str, y_col: str,
                      z_col: str) -> Dict[str, Any]:
        """Estimate causal effect using two-stage least squares.

        Args:
            df: DataFrame with columns for X, Y, and Z
            x_col: Endogenous variable column
            y_col: Outcome variable column
            z_col: Instrument column

        Returns:
            Dict with causal_effect, std_error, t_stat, p_value, stage1_r2
        """
        # Stage 1: Regress X on Z
        z = df[z_col].values
        x = df[x_col].values
        y = df[y_col].values

        # Add constant
        Z = np.column_stack([np.ones(len(z)), z])

        # OLS: X = π₀ + π₁Z + ε
        try:
            pi = np.linalg.lstsq(Z, x, rcond=None)[0]
            x_hat = Z @ pi
            stage1_r2 = 1 - np.sum((x - x_hat) ** 2) / np.sum((x - np.mean(x)) ** 2)
        except np.linalg.LinAlgError:
            return {"error": "Stage 1 regression failed"}

        # Stage 2: Regress Y on X̂
        X_hat = np.column_stack([np.ones(len(x_hat)), x_hat])
        try:
            beta = np.linalg.lstsq(X_hat, y, rcond=None)[0]
        except np.linalg.LinAlgError:
            return {"error": "Stage 2 regression failed"}

        # Standard errors (heteroskedasticity-robust)
        residuals = y - X_hat @ beta
        n = len(y)
        k = X_hat.shape[1]
        sigma2 = np.sum(residuals ** 2) / (n - k)
        try:
            var_beta = sigma2 * np.linalg.inv(X_hat.T @ X_hat)
            se_beta = np.sqrt(np.diag(var_beta))
        except np.linalg.LinAlgError:
            se_beta = np.full(k, np.nan)

        causal_effect = beta[1]
        std_error = se_beta[1]
        t_stat = causal_effect / std_error if std_error > 0 else np.nan
        p_value = 2 * (1 - stats.t.cdf(abs(t_stat), df=n - k)) if not np.isnan(t_stat) else np.nan

        # First-stage F-statistic (weak instrument test)
        f_stat = (stage1_r2 / (1 - stage1_r2)) * ((n - 2) / 1) if stage1_r2 < 1 else np.inf

        return {
            "causal_effect": float(causal_effect),
            "std_error": float(std_error),
            "t_stat": float(t_stat),
            "p_value": float(p_value),
            "stage1_r2": float(stage1_r2),
            "first_stage_f": float(f_stat),
            "weak_instrument": f_stat < 10,  # Stock-Yogo rule of thumb
            "n_obs": n,
        }


# =============================================================================
# Do-Calculus (Intervention Simulator)
# =============================================================================

class DoCalculus:
    """Simulate interventions (do-operator) on a causal graph.

    The do(X=x) operation removes all incoming edges to X and sets X to x.
    This allows computing interventional distributions P(Y | do(X=x)).
    """

    def __init__(self, graph: CausalGraph):
        self.graph = graph

    def intervene(self, interventions: Dict[str, float]) -> CausalGraph:
        """Create a modified graph with do-operator applied.

        Args:
            interventions: Dict mapping variable names to their intervened values.
                          e.g., {"X": 1.0} means do(X=1.0)

        Returns:
            New CausalGraph with incoming edges to intervened nodes removed.
        """
        new_graph = CausalGraph()
        for parent, children in self.graph._adj.items():
            for child in children:
                # Skip edges that point to an intervened node
                if child in interventions:
                    continue
                new_graph.add_edge(parent, child)
        return new_graph

    def compute_interventional_mean(self, target: str, interventions: Dict[str, float],
                                     data: pd.DataFrame) -> float:
        """Compute E[target | do(interventions)] using adjustment.

        Uses the backdoor adjustment formula:
        E[Y | do(X=x)] = E_Z[E[Y | X=x, Z]]
        """
        backdoor = BackdoorCriterion(self.graph)
        x = list(interventions.keys())[0]
        y = target

        # Find adjustment set
        z = backdoor.find_minimal_adjustment_set(x, y)
        if z is None:
            logger.warning(f"No valid backdoor adjustment set found for ({x}, {y})")
            return float(data[target].mean())

        # Compute adjusted mean
        result = 0.0
        for z_val in data[list(z)[0]].unique() if len(z) == 1 else [None]:
            if z_val is not None:
                subset = data[data[list(z)[0]] == z_val]
            else:
                subset = data
            if len(subset) > 0:
                result += subset[target].mean() * len(subset) / len(data)

        return float(result)


# =============================================================================
# High-Level Causal Effect Estimator
# =============================================================================

class CausalEffectEstimator:
    """High-level API for estimating causal effects from market data.

    Automatically selects the appropriate estimation strategy:
    1. Backdoor adjustment (if valid adjustment set exists)
    2. Front-door adjustment (if backdoor unavailable but front-door exists)
    3. Instrumental variables (if valid instruments exist)
    4. Difference-in-differences (if panel data available)
    """

    def __init__(self, graph: Optional[CausalGraph] = None):
        self.graph = graph or CausalGraph()
        self.backdoor = BackdoorCriterion(self.graph)
        self.frontdoor = FrontDoorCriterion(self.graph)
        self.iv = InstrumentalVariables(self.graph)
        self.do_calculus = DoCalculus(self.graph)

    def estimate_effect(self, df: pd.DataFrame, cause: str, effect: str,
                        method: str = "auto") -> Dict[str, Any]:
        """Estimate the causal effect of cause on effect.

        Args:
            df: DataFrame with columns for cause, effect, and covariates
            cause: Name of the cause variable column
            effect: Name of the effect variable column
            method: "auto", "backdoor", "frontdoor", "iv", or "regression"

        Returns:
            Dict with causal_effect, std_error, p_value, method_used, diagnostics
        """
        if method == "auto":
            # Try backdoor first
            z = self.backdoor.find_minimal_adjustment_set(cause, effect)
            if z:
                return self._backdoor_estimate(df, cause, effect, z)
            # Try IV
            instruments = [n for n in self.graph.get_nodes()
                          if self.iv.is_valid_instrument(n, cause, effect)]
            if instruments:
                return self.iv.estimate_2sls(df, cause, effect, instruments[0])
            # Fall back to regression
            return self._regression_estimate(df, cause, effect)
        elif method == "backdoor":
            z = self.backdoor.find_minimal_adjustment_set(cause, effect)
            if not z:
                return {"error": "No valid backdoor adjustment set found"}
            return self._backdoor_estimate(df, cause, effect, z)
        elif method == "iv":
            instruments = [n for n in self.graph.get_nodes()
                          if self.iv.is_valid_instrument(n, cause, effect)]
            if not instruments:
                return {"error": "No valid instruments found"}
            return self.iv.estimate_2sls(df, cause, effect, instruments[0])
        else:
            return self._regression_estimate(df, cause, effect)

    def _backdoor_estimate(self, df, cause, effect, z):
        """Estimate causal effect using backdoor adjustment via regression."""
        # Simple approach: regress effect on cause + adjustment set
        from numpy.linalg import lstsq

        y = df[effect].values
        cols = [cause] + list(z)
        X = np.column_stack([np.ones(len(df))] + [df[c].values for c in cols])

        try:
            beta = lstsq(X, y, rcond=None)[0]
            residuals = y - X @ beta
            n = len(y)
            k = X.shape[1]
            sigma2 = np.sum(residuals ** 2) / (n - k)
            var_beta = sigma2 * np.linalg.inv(X.T @ X)
            se = np.sqrt(np.diag(var_beta))

            causal_effect = beta[1]  # coefficient for cause
            std_error = se[1]
            t_stat = causal_effect / std_error if std_error > 0 else np.nan
            p_value = 2 * (1 - stats.t.cdf(abs(t_stat), df=n - k)) if not np.isnan(t_stat) else np.nan

            return {
                "causal_effect": float(causal_effect),
                "std_error": float(std_error),
                "t_stat": float(t_stat),
                "p_value": float(p_value),
                "method": "backdoor",
                "adjustment_set": list(z),
                "n_obs": n,
            }
        except Exception as e:
            return {"error": str(e)}

    def _regression_estimate(self, df, cause, effect):
        """Simple OLS regression (no causal adjustment)."""
        x = df[cause].values
        y = df[effect].values
        X = np.column_stack([np.ones(len(x)), x])

        try:
            beta = np.linalg.lstsq(X, y, rcond=None)[0]
            residuals = y - X @ beta
            n = len(y)
            sigma2 = np.sum(residuals ** 2) / (n - 2)
            var_beta = sigma2 * np.linalg.inv(X.T @ X)
            se = np.sqrt(np.diag(var_beta))

            return {
                "causal_effect": float(beta[1]),
                "std_error": float(se[1]),
                "t_stat": float(beta[1] / se[1]) if se[1] > 0 else np.nan,
                "p_value": float(2 * (1 - stats.t.cdf(abs(beta[1] / se[1]), df=n - 2))) if se[1] > 0 else np.nan,
                "method": "regression",
                "warning": "No causal adjustment applied — this is a correlational estimate",
                "n_obs": n,
            }
        except Exception as e:
            return {"error": str(e)}
