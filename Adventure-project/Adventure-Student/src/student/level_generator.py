"""TODO: build a canonical level using the injected terrain generator."""
import random
from collections import deque
 
from src.api import (
    CharacterDefinition, GenerationFailure, LevelDefinition, LevelSpecification,
    Position, TerrainGeneratorContract,
)
 
# The 4 neighbors as (row change, column change): up, down, left, right.
DIRECTIONS = [(-1, 0), (1, 0), (0, -1), (0, 1)]
 
 
class LevelGenerator:
    """Use the supplied TerrainGeneratorContract; do not instantiate a replacement."""
 
    def __init__(self, terrain_generator: TerrainGeneratorContract) -> None:
        self._terrain_generator = terrain_generator  # keep the one we were given
 
    def generate_level(self, specification: LevelSpecification, seed: int) -> LevelDefinition:
        # This first version only builds the introductory world (no extras).
        if specification.artifact_count > 0 or specification.enemy_count > 0:
            raise GenerationFailure("LevelGenerator", "artifacts and enemies are not supported yet")
        if specification.require_alternate_path or specification.min_branch_tiles > 0:
            raise GenerationFailure("LevelGenerator", "branches and loops are not supported yet")
 
        rng = random.Random(seed)
 
        for attempt in range(specification.max_attempts):
            terrain = self._terrain_generator.generate_terrain(
                specification.terrain_spec, seed + attempt
            )
 
            # On a path, the two ends are the floor cells with only one floor neighbor.
            ends = self._find_dead_ends(terrain)
            if len(ends) < 2:
                continue
            start, exit_cell = rng.sample(ends, 2)
 
            # Check the route length (moves) and that EXIT still fits in max_turns.
            moves = self._count_moves(terrain, start, exit_cell)
            if moves is None:
                continue
            if moves < specification.min_route_moves or moves > specification.max_route_moves:
                continue
            if moves + 1 > specification.max_turns:  # +1 for the EXIT action
                continue
 
            return LevelDefinition(
                level_id=specification.level_id,
                profile_id=specification.profile_id,
                seed=seed,
                terrain=terrain,
                start=start,
                exit=exit_cell,
                character=CharacterDefinition(specification.agent_id),
            )
 
        raise GenerationFailure("LevelGenerator", "no valid level found within max_attempts")
 
    def _floor_neighbors(self, terrain, cell):
        """List the floor cells next to this cell."""
        neighbors = []
        for row_change, column_change in DIRECTIONS:
            neighbor = Position(cell.row + row_change, cell.column + column_change)
            if terrain.is_traversable(neighbor):
                neighbors.append(neighbor)
        return neighbors
 
    def _find_dead_ends(self, terrain):
        """List the floor cells that have exactly one floor neighbor."""
        ends = []
        for row in range(terrain.rows):
            for column in range(terrain.columns):
                cell = Position(row, column)
                if terrain.is_traversable(cell) and len(self._floor_neighbors(terrain, cell)) == 1:
                    ends.append(cell)
        return ends
 
    def _count_moves(self, terrain, start, goal):
        """Fewest moves from start to goal (BFS with a queue), or None."""
        queue = deque()
        queue.append((start, 0))  # each item: (cell, moves so far)
        visited = {start}
 
        while len(queue) > 0:
            cell, moves = queue.popleft()
            if cell == goal:
                return moves
            for neighbor in self._floor_neighbors(terrain, cell):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, moves + 1))
 
        return None
 
