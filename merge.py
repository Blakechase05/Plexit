"""
Tree-based rectangle merging algorithm.

This module implements an optimal rectangle merging strategy that:
1. Starts from the largest rectangle and works outwards
2. Uses a tree structure to explore all possible merge combinations
3. Scores solutions based on total area maximization
4. Ensures only valid rectangular merges (no unusual shapes)
"""

from typing import List, Tuple, Set, Optional
from dataclasses import dataclass, field


# Type aliases for clarity
Point = Tuple[float, float]
Rectangle = Tuple[Point, Point]  # ((x0, y0), (x1, y1))


@dataclass
class MergeNode:
    """
    Represents a node in the merge tree.
    Each node contains a possible configuration of rectangles.
    """
    rectangles: List[Rectangle]
    total_count: int = field(init=False)
    total_area: float = field(init=False)
    merged_pairs: Set[Tuple[int, int]] = field(default_factory=set)
    parent: Optional['MergeNode'] = None
    children: List['MergeNode'] = field(default_factory=list)

    def __post_init__(self):
        self.total_count = len(self.rectangles)
        self.total_area = sum(calculate_area(r) for r in self.rectangles)

    def score(self) -> float:
        """
        Score this configuration. Higher is better.
        Prioritizes: fewer rectangles, then larger average area.
        """
        if self.total_count == 0:
            return 0
        # Primary: minimize count (negative so fewer is better)
        # Secondary: maximize total area
        return -self.total_count * 1000000 + self.total_area


def calculate_area(rect: Rectangle) -> float:
    """Calculate the area of a rectangle."""
    (x0, y0), (x1, y1) = rect
    return abs(x1 - x0) * abs(y1 - y0)


def rectangles_are_adjacent(r1: Rectangle, r2: Rectangle) -> bool:
    """
    Check if two rectangles share an edge (are adjacent).
    Returns True if they share a complete edge.
    """
    (x0_a, y0_a), (x1_a, y1_a) = r1
    (x0_b, y0_b), (x1_b, y1_b) = r2

    # Ensure coordinates are ordered
    x0_a, x1_a = min(x0_a, x1_a), max(x0_a, x1_a)
    y0_a, y1_a = min(y0_a, y1_a), max(y0_a, y1_a)
    x0_b, x1_b = min(x0_b, x1_b), max(x0_b, x1_b)
    y0_b, y1_b = min(y0_b, y1_b), max(y0_b, y1_b)

    # Check if they share a vertical edge (left or right)
    if x1_a == x0_b or x1_b == x0_a:  # Adjacent vertically
        # Check if they have overlapping y-ranges
        y_overlap_start = max(y0_a, y0_b)
        y_overlap_end = min(y1_a, y1_b)
        if y_overlap_start < y_overlap_end:
            return True

    # Check if they share a horizontal edge (top or bottom)
    if y1_a == y0_b or y1_b == y0_a:  # Adjacent horizontally
        # Check if they have overlapping x-ranges
        x_overlap_start = max(x0_a, x0_b)
        x_overlap_end = min(x1_a, x1_b)
        if x_overlap_start < x_overlap_end:
            return True

    return False


def can_merge_into_rectangle(r1: Rectangle, r2: Rectangle) -> bool:
    """
    Check if two rectangles can be merged into a single valid rectangle.
    This requires them to be adjacent and aligned such that the result is rectangular.
    """
    if not rectangles_are_adjacent(r1, r2):
        return False

    (x0_a, y0_a), (x1_a, y1_a) = r1
    (x0_b, y0_b), (x1_b, y1_b) = r2

    # Ensure coordinates are ordered
    x0_a, x1_a = min(x0_a, x1_a), max(x0_a, x1_a)
    y0_a, y1_a = min(y0_a, y1_a), max(y0_a, y1_a)
    x0_b, x1_b = min(x0_b, x1_b), max(x0_b, x1_b)
    y0_b, y1_b = min(y0_b, y1_b), max(y0_b, y1_b)

    # Horizontal merge (side by side)
    if y0_a == y0_b and y1_a == y1_b:  # Same height
        if x1_a == x0_b or x1_b == x0_a:  # Adjacent
            return True

    # Vertical merge (stacked)
    if x0_a == x0_b and x1_a == x1_b:  # Same width
        if y1_a == y0_b or y1_b == y0_a:  # Adjacent
            return True

    return False


def merge_rectangles(r1: Rectangle, r2: Rectangle) -> Optional[Rectangle]:
    """
    Merge two rectangles into one if possible.
    Returns the merged rectangle or None if they can't be merged.
    """
    if not can_merge_into_rectangle(r1, r2):
        return None

    (x0_a, y0_a), (x1_a, y1_a) = r1
    (x0_b, y0_b), (x1_b, y1_b) = r2

    # Ensure coordinates are ordered
    x0_a, x1_a = min(x0_a, x1_a), max(x0_a, x1_a)
    y0_a, y1_a = min(y0_a, y1_a), max(y0_a, y1_a)
    x0_b, x1_b = min(x0_b, x1_b), max(x0_b, x1_b)
    y0_b, y1_b = min(y0_b, y1_b), max(y0_b, y1_b)

    # Create bounding box
    x_min = min(x0_a, x0_b)
    x_max = max(x1_a, x1_b)
    y_min = min(y0_a, y0_b)
    y_max = max(y1_a, y1_b)

    return ((x_min, y_min), (x_max, y_max))


def find_all_merge_candidates(rectangles: List[Rectangle],
                              already_merged: Set[Tuple[int, int]]) -> List[Tuple[int, int, Rectangle, float]]:
    """
    Find all valid pairs of rectangles that can be merged.
    Returns list of (index1, index2, merged_rect, area_gain) sorted by area_gain descending.
    """
    candidates = []

    for i in range(len(rectangles)):
        for j in range(i + 1, len(rectangles)):
            # Skip if we've already explored this merge in ancestor nodes
            pair = (i, j) if i < j else (j, i)
            if pair in already_merged:
                continue

            merged = merge_rectangles(rectangles[i], rectangles[j])
            if merged:
                # Calculate the area gain from merging
                area_before = calculate_area(rectangles[i]) + calculate_area(rectangles[j])
                area_after = calculate_area(merged)
                area_gain = area_after - area_before

                candidates.append((i, j, merged, area_after))

    # Sort by area of resulting rectangle (largest first)
    candidates.sort(key=lambda x: x[3], reverse=True)
    return candidates


def build_merge_tree(root: MergeNode, max_depth: int = 20, current_depth: int = 0) -> None:
    """
    Recursively build the merge tree by exploring all possible merge options.
    Uses depth-first exploration with a maximum depth limit.
    """
    if current_depth >= max_depth:
        return

    # Find all possible merges from this configuration
    candidates = find_all_merge_candidates(root.rectangles, root.merged_pairs)

    if not candidates:
        # Leaf node - no more merges possible
        return

    # For each candidate merge, create a child node
    for i, j, merged_rect, _ in candidates:
        # Create new rectangle list with the merge applied
        new_rectangles = []
        for k, rect in enumerate(root.rectangles):
            if k != i and k != j:
                new_rectangles.append(rect)
        new_rectangles.append(merged_rect)

        # Track which pairs have been merged in the ancestry
        new_merged_pairs = root.merged_pairs.copy()
        new_merged_pairs.add((i, j) if i < j else (j, i))

        # Create child node
        child = MergeNode(
            rectangles=new_rectangles,
            merged_pairs=new_merged_pairs,
            parent=root
        )
        root.children.append(child)

        # Recursively explore this branch
        build_merge_tree(child, max_depth, current_depth + 1)


def find_best_solution(root: MergeNode) -> MergeNode:
    """
    Traverse the entire tree to find the configuration with the best score.
    """
    best = root
    best_score = root.score()

    # DFS to find the best leaf or internal node
    stack = [root]
    while stack:
        node = stack.pop()

        score = node.score()
        if score > best_score:
            best = node
            best_score = score

        stack.extend(node.children)

    return best


def optimize_rectangles(rectangles: List[Rectangle], max_depth: int = 20,
                        verbose: bool = False) -> List[Rectangle]:
    """
    Main entry point for the rectangle merging optimization.

    Args:
        rectangles: List of rectangles to optimize
        max_depth: Maximum depth for tree exploration (prevents infinite loops)
        verbose: Print progress information

    Returns:
        Optimized list of rectangles with minimal count and maximal area coverage
    """
    if not rectangles:
        return []

    if verbose:
        print(f"Starting optimization with {len(rectangles)} rectangles")
        print(f"Initial total area: {sum(calculate_area(r) for r in rectangles):.2f}")

    # Sort rectangles by area (largest first) - this influences the tree exploration
    rectangles_sorted = sorted(rectangles, key=calculate_area, reverse=True)

    # Create root node
    root = MergeNode(rectangles=rectangles_sorted)

    if verbose:
        print(f"Building merge tree (max depth: {max_depth})...")

    # Build the complete merge tree
    build_merge_tree(root, max_depth=max_depth)

    if verbose:
        # Count total nodes
        total_nodes = 1
        stack = [root]
        while stack:
            node = stack.pop()
            total_nodes += len(node.children)
            stack.extend(node.children)
        print(f"Tree built with {total_nodes} nodes")

    # Find the best solution
    best = find_best_solution(root)

    if verbose:
        print(f"\nOptimal solution found:")
        print(f"  Rectangles: {best.total_count} (reduced from {len(rectangles)})")
        print(f"  Total area: {best.total_area:.2f}")
        print(f"  Average area per rectangle: {best.total_area/best.total_count:.2f}")

    return best.rectangles


def merge_greedy(rectangles: List[Rectangle], verbose: bool = False) -> List[Rectangle]:
    """
    Fast greedy algorithm that always takes the best merge at each step.
    Prioritizes creating larger rectangles to minimize total count.

    Args:
        rectangles: List of rectangles to merge
        verbose: Print progress information

    Returns:
        Merged list of rectangles
    """
    # Start with largest rectangles first
    current = sorted(rectangles, key=calculate_area, reverse=True)

    if verbose:
        print(f"Starting greedy merge with {len(current)} rectangles")
        initial_area = sum(calculate_area(r) for r in current)
        print(f"Initial total area: {initial_area:.2f}")

    iteration = 0
    while True:
        best_merge = None
        best_score = -float('inf')
        best_indices = None

        # Find the best merge among all possible pairs
        for i in range(len(current)):
            for j in range(i + 1, len(current)):
                merged = merge_rectangles(current[i], current[j])
                if merged:
                    # Score based on resulting rectangle area
                    merged_area = calculate_area(merged)

                    # Prioritize larger resulting rectangles
                    score = merged_area

                    if score > best_score:
                        best_score = score
                        best_merge = merged
                        best_indices = (i, j)

        if best_merge is None:
            # No more merges possible
            break

        # Apply the best merge
        i, j = best_indices
        new_current = []
        for k, rect in enumerate(current):
            if k != i and k != j:
                new_current.append(rect)
        new_current.append(best_merge)

        current = new_current
        iteration += 1

        if verbose:
            print(f"  Iteration {iteration}: Merged 2 rectangles -> {len(current)} remaining (area: {best_score:.2f})")

    if verbose:
        final_area = sum(calculate_area(r) for r in current)
        print(f"\nGreedy merge complete:")
        print(f"  Final count: {len(current)} rectangles")
        print(f"  Final area: {final_area:.2f}")
        print(f"  Reduction: {len(rectangles) - len(current)} rectangles merged")

    return current


def merge_optimal_fast(rectangles: List[Rectangle], verbose: bool = False,
                       max_iterations: int = 1000) -> List[Rectangle]:
    """
    Optimized merge algorithm that prioritizes finding the largest possible rectangle first,
    then optimizes the remaining rectangles.

    Args:
        rectangles: List of rectangles to merge
        verbose: Print progress information
        max_iterations: Maximum iterations to prevent infinite loops

    Returns:
        Merged list of rectangles with the largest rectangle maximized
    """
    if not rectangles:
        return []

    if verbose:
        print(f"Starting optimized merge with {len(rectangles)} rectangles")
        initial_area = sum(calculate_area(r) for r in rectangles)
        print(f"Initial total area: {initial_area:.2f}")

    # Use the max-first strategy
    result = _merge_maximize_largest_first(rectangles, verbose=verbose, max_iterations=max_iterations)

    if verbose:
        final_area = sum(calculate_area(r) for r in result)
        largest_area = max(calculate_area(r) for r in result) if result else 0
        print(f"\nOptimized merge complete:")
        print(f"  Final count: {len(result)} rectangles (from {len(rectangles)})")
        print(f"  Final area: {final_area:.2f}")
        print(f"  Largest rectangle area: {largest_area:.2f}")
        print(f"  Reduction: {len(rectangles) - len(result)} rectangles merged")

    return result


def _merge_maximize_largest_first(rectangles: List[Rectangle], verbose: bool = False,
                                  max_iterations: int = 1000) -> List[Rectangle]:
    """
    Strategy that exhaustively searches for the largest possible rectangle first,
    then optimizes the remaining rectangles.

    This uses a branch-and-bound approach to explore different merge sequences
    and find the one that produces the largest single rectangle.
    """
    if not rectangles:
        return []

    # Phase 1: Find the merge sequence that produces the largest single rectangle
    best_solution = rectangles
    best_max_area = max(calculate_area(r) for r in rectangles)

    if verbose:
        print(f"  Phase 1: Searching for largest possible rectangle...")
        print(f"  Initial max area: {best_max_area:.2f}")

    # Try different merge sequences using DFS with pruning
    def explore_merges(current_rects: List[Rectangle], depth: int = 0, max_depth: int = 100) -> None:
        nonlocal best_solution, best_max_area

        if depth > max_depth:
            return

        current_max_area = max(calculate_area(r) for r in current_rects)

        # Update best solution if we found a larger max rectangle
        if current_max_area > best_max_area:
            best_max_area = current_max_area
            best_solution = current_rects
            if verbose:
                print(f"    Found larger rectangle: {best_max_area:.2f} (depth {depth}, {len(current_rects)} rects)")

        # Early termination: if current max equals total area, we can't do better
        total_area = sum(calculate_area(r) for r in current_rects)
        if abs(current_max_area - total_area) < 0.01:
            return

        # Find all possible merges, prioritized by resulting area
        merge_candidates = []
        for i in range(len(current_rects)):
            for j in range(i + 1, len(current_rects)):
                merged = merge_rectangles(current_rects[i], current_rects[j])
                if merged:
                    merged_area = calculate_area(merged)
                    merge_candidates.append((i, j, merged, merged_area))

        # Sort by merged area (largest first) - prioritize creating large rectangles
        merge_candidates.sort(key=lambda x: x[3], reverse=True)

        # Prune: only explore top candidates that could beat current best
        pruned_candidates = []
        for i, j, merged, area in merge_candidates:
            # Could this merge lead to a better solution?
            # More aggressive exploration - keep candidates within 70% of best OR large absolute area
            if area > best_max_area * 0.7 or area > best_max_area * 0.5:
                pruned_candidates.append((i, j, merged, area))

        # Explore more promising merges with adaptive branching
        # At shallow depths, explore more; at deep depths, focus on top candidates
        max_branches = max(5, 15 - depth // 5)
        for (i, j, merged, area) in pruned_candidates[:max_branches]:
            new_rects = [r for k, r in enumerate(current_rects) if k != i and k != j]
            new_rects.append(merged)
            explore_merges(new_rects, depth + 1, max_depth)

    # Start the search
    explore_merges(rectangles)

    if verbose:
        print(f"  Phase 1 complete: Largest rectangle area = {best_max_area:.2f}")
        print(f"  Phase 2: Optimizing remaining {len(best_solution)} rectangles...")

    # Phase 2: Continue merging remaining rectangles greedily
    current = list(best_solution)
    iteration = 0
    changed = True

    while changed and iteration < max_iterations:
        changed = False
        iteration += 1

        # Find all possible merges
        merges = []
        for i in range(len(current)):
            for j in range(i + 1, len(current)):
                merged = merge_rectangles(current[i], current[j])
                if merged:
                    merged_area = calculate_area(merged)
                    area_i = calculate_area(current[i])
                    area_j = calculate_area(current[j])

                    # Prioritize merges that create large rectangles
                    score = merged_area * 100
                    merges.append((i, j, merged, score))

        if not merges:
            break

        # Sort by score
        merges.sort(key=lambda x: x[3], reverse=True)

        # Apply all non-conflicting merges
        used_indices = set()
        new_rectangles = []

        for i, j, merged, score in merges:
            if i not in used_indices and j not in used_indices:
                new_rectangles.append(merged)
                used_indices.add(i)
                used_indices.add(j)
                changed = True

        # Add rectangles that weren't merged
        for k, rect in enumerate(current):
            if k not in used_indices:
                new_rectangles.append(rect)

        current = new_rectangles

    if verbose:
        print(f"  Phase 2 complete: {len(current)} final rectangles")

    return current


def _merge_with_lookahead(rectangles: List[Rectangle], verbose: bool = False) -> List[Rectangle]:
    """
    Merge strategy with 2-step lookahead to avoid greedy pitfalls.
    """
    current = sorted(rectangles, key=calculate_area, reverse=True)
    changed = True

    while changed:
        changed = False
        best_merge = None
        best_score = -1
        best_indices = None

        # For each possible merge, evaluate how many follow-up merges it enables
        for i in range(len(current)):
            for j in range(i + 1, len(current)):
                merged = merge_rectangles(current[i], current[j])
                if not merged:
                    continue

                # Create hypothetical state after this merge
                temp = [r for k, r in enumerate(current) if k != i and k != j]
                temp.append(merged)

                # Count how many additional merges are possible
                additional_merges = 0
                for m in range(len(temp)):
                    for n in range(m + 1, len(temp)):
                        if can_merge_into_rectangle(temp[m], temp[n]):
                            additional_merges += 1

                # Score: prioritize merges that create large rectangles and enable more merges
                merged_area = calculate_area(merged)
                score = merged_area * 10 + additional_merges * 100

                if score > best_score:
                    best_score = score
                    best_merge = merged
                    best_indices = (i, j)

        if best_merge is not None:
            i, j = best_indices
            new_current = [r for k, r in enumerate(current) if k != i and k != j]
            new_current.append(best_merge)
            current = new_current
            changed = True

    return current


def _merge_aligned_first(rectangles: List[Rectangle], verbose: bool = False) -> List[Rectangle]:
    """
    Prioritize merging rectangles that are perfectly aligned (same width or height).
    """
    current = list(rectangles)
    changed = True

    while changed:
        changed = False
        best_merge = None
        best_score = -1
        best_indices = None

        for i in range(len(current)):
            for j in range(i + 1, len(current)):
                merged = merge_rectangles(current[i], current[j])
                if not merged:
                    continue

                (x0_a, y0_a), (x1_a, y1_a) = current[i]
                (x0_b, y0_b), (x1_b, y1_b) = current[j]

                # Normalize coordinates
                x0_a, x1_a = min(x0_a, x1_a), max(x0_a, x1_a)
                y0_a, y1_a = min(y0_a, y1_a), max(y0_a, y1_a)
                x0_b, x1_b = min(x0_b, x1_b), max(x0_b, x1_b)
                y0_b, y1_b = min(y0_b, y1_b), max(y0_b, y1_b)

                width_a = x1_a - x0_a
                height_a = y1_a - y0_a
                width_b = x1_b - x0_b
                height_b = y1_b - y0_b

                # Bonus for perfect alignment
                alignment_bonus = 0
                if width_a == width_b:
                    alignment_bonus += 1000
                if height_a == height_b:
                    alignment_bonus += 1000

                merged_area = calculate_area(merged)
                score = merged_area + alignment_bonus

                if score > best_score:
                    best_score = score
                    best_merge = merged
                    best_indices = (i, j)

        if best_merge is not None:
            i, j = best_indices
            new_current = [r for k, r in enumerate(current) if k != i and k != j]
            new_current.append(best_merge)
            current = new_current
            changed = True

    return current


def _merge_parallel_improved(rectangles: List[Rectangle], verbose: bool = False,
                             max_iterations: int = 1000) -> List[Rectangle]:
    """
    Improved parallel merge that considers merge quality more carefully.
    """
    current = sorted(rectangles, key=calculate_area, reverse=True)
    iteration = 0
    changed = True

    while changed and iteration < max_iterations:
        changed = False
        iteration += 1

        # Find all possible merges with better scoring
        merges = []
        for i in range(len(current)):
            for j in range(i + 1, len(current)):
                merged = merge_rectangles(current[i], current[j])
                if merged:
                    merged_area = calculate_area(merged)
                    area_i = calculate_area(current[i])
                    area_j = calculate_area(current[j])

                    # Better score: prioritize merges that maximize area gain
                    # and create larger rectangles
                    area_ratio = merged_area / (area_i + area_j)
                    score = merged_area * 100 + area_ratio * 10

                    merges.append((i, j, merged, score))

        if not merges:
            break

        # Sort by score (best first)
        merges.sort(key=lambda x: x[3], reverse=True)

        # Apply all non-conflicting merges greedily
        used_indices = set()
        new_rectangles = []

        for i, j, merged, score in merges:
            if i not in used_indices and j not in used_indices:
                new_rectangles.append(merged)
                used_indices.add(i)
                used_indices.add(j)
                changed = True

        # Add rectangles that weren't merged
        for k, rect in enumerate(current):
            if k not in used_indices:
                new_rectangles.append(rect)

        current = new_rectangles

    return current
