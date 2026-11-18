import random

from src.api import GenerationFailure, Terrain, TerrainGenerationSpec, TerrainTopology


class TerrainGenerator:
    """Keep state local; identical inputs must also agree across fresh instances."""

    def __init__(self) -> None:
        pass  # no stored state, so every instance gives the same answer

    def generate_terrain(self, specification: TerrainGenerationSpec, seed: int) -> Terrain:
        rng = random.Random(seed)  # same seed -> same random choices

        # A 2D list: grid[row][column]. Start with all walls ("#").
        grid = [["#"] * specification.columns for _ in range(specification.rows)]

        if specification.topology == TerrainTopology.STRAIGHT_PATH:
            self._carve_straight_path(grid, specification, rng)
        elif specification.topology == TerrainTopology.BENT_PATH:
            self._carve_bent_path(grid, specification, rng)
        else:
            raise GenerationFailure(
                "TerrainGenerator", "only STRAIGHT_PATH and BENT_PATH are supported"
            )

        # Turn each row (a list of characters) into a string.
        rows = []
        for line in grid:
            rows.append("".join(line))
        return Terrain(tuple(rows))

    def _carve_straight_path(self, grid, spec, rng):
        # A path needs at least 2 cells (a start and a different exit).
        shortest = max(spec.min_open_tiles, 2)

        # The longest path that fits along a row, and along a column.
        longest_in_row = min(spec.max_open_tiles, spec.columns)
        longest_in_column = min(spec.max_open_tiles, spec.rows)

        choices = []  # each choice: (is_horizontal, longest length)
        if shortest <= longest_in_row:
            choices.append((True, longest_in_row))
        if shortest <= longest_in_column:
            choices.append((False, longest_in_column))
        if len(choices) == 0:
            raise GenerationFailure("TerrainGenerator", "no straight path fits this specification")

        is_horizontal, longest = rng.choice(choices)
        length = rng.randint(shortest, longest)

        if is_horizontal:
            row = rng.randrange(spec.rows)
            first = rng.randrange(spec.columns - length + 1)
            for i in range(length):
                grid[row][first + i] = "."
        else:
            column = rng.randrange(spec.columns)
            first = rng.randrange(spec.rows - length + 1)
            for i in range(length):
                grid[first + i][column] = "."

    def _carve_bent_path(self, grid, spec, rng):
        # An "L" shape: a horizontal arm that is `wide` cells long and a
        # vertical arm that is `tall` cells long. They share one corner cell,
        # so the number of open cells is wide + tall - 1.
        shapes = []  # each shape: (wide, tall)
        for wide in range(2, spec.columns + 1):
            for tall in range(2, spec.rows + 1):
                open_cells = wide + tall - 1
                if spec.min_open_tiles <= open_cells <= spec.max_open_tiles:
                    shapes.append((wide, tall))
        if len(shapes) == 0:
            raise GenerationFailure("TerrainGenerator", "no bent path fits this specification")

        wide, tall = rng.choice(shapes)
        top = rng.randrange(spec.rows - tall + 1)
        left = rng.randrange(spec.columns - wide + 1)

        # The corner is at one end of each arm, so the L can face 4 ways.
        corner_row = rng.choice([top, top + tall - 1])
        corner_column = rng.choice([left, left + wide - 1])

        for i in range(wide):
            grid[corner_row][left + i] = "."      # horizontal arm
        for i in range(tall):
            grid[top + i][corner_column] = "."    # vertical arm