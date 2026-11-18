"""TODO: select one public action from each immutable world observation."""

import heapq
 
from src.api import Position, WorldAction, WorldActionType
 
# The 4 moves as (move, row change, column change).
MOVES = [
    (WorldActionType.MOVE_NORTH, -1, 0),  # up    = row - 1
    (WorldActionType.MOVE_SOUTH, 1, 0),   # down  = row + 1
    (WorldActionType.MOVE_WEST, 0, -1),   # left  = column - 1
    (WorldActionType.MOVE_EAST, 0, 1),    # right = column + 1
]
 
MAX_REWARDS = 6                # plan with at most the 6 nearest rewards (keeps it fast)
IMPOSSIBLE = float("-inf")     # score of a plan that cannot be done
PATROL_EXTRA = 3               # extra cost of a cell on a patrol's route (we prefer to walk around)
 
 
class AgentController:
    """A new controller is constructed for each run; arrival still needs EXIT."""
 
    def __init__(self) -> None:
        # Remembered results, so the same search is not repeated every turn.
        self.memory = {}
 
    def choose_action(self, state, agent_id: str) -> WorldAction:
        here = state.agent_position
        exit_cell = state.exit_position
        rate = state.deduction_rate
 
        # Cheapest costs from here, and the first action toward every cell.
        here_costs, here_first = self.routes_from(state, here)
 
        # Only rewards that can be reached and are worth more than 1 extra action.
        rewards = []
        if WorldActionType.COLLECT in state.allowed_actions:
            for artifact in state.level.artifacts:
                if artifact.artifact_id in state.collected_artifact_ids:
                    continue
                if artifact.value > rate and artifact.position in here_costs:
                    rewards.append(artifact)
        rewards.sort(key=lambda reward: here_costs[reward.position])  # nearest first
        rewards = rewards[:MAX_REWARDS]
 
        # Costs from each reward to every other cell (needed to compare orders).
        costs = {here: here_costs}
        for reward in rewards:
            costs[reward.position] = self.routes_from(state, reward.position)[0]
 
        # Accepted actions we still have (the action limit and any deadline).
        limit = state.max_turns
        if state.deadline_turn is not None:
            limit = min(limit, state.deadline_turn)
        budget = limit - state.turn
 
        score, order = self.best_plan(here, rewards, budget, costs, exit_cell, rate)
 
        if len(order) > 0:
            target = order[0].position            # go to the first reward of the best plan
            if target == here:
                action = WorldAction(WorldActionType.COLLECT, target_id=order[0].artifact_id)
            else:
                action = here_first[target][0]
        elif here == exit_cell:
            action = WorldAction(WorldActionType.EXIT)
        elif exit_cell in here_first:
            action = here_first[exit_cell][0]
        else:
            return WorldAction.wait()             # no route found
 
        return self.avoid_patrols(state, action)
 
    def best_plan(self, current, remaining, budget, costs, exit_cell, rate):
        """RECURSION. Return (score, order of rewards to collect) from `current`.
 
        score = values of the rewards collected - rate * cost of everything we still do.
        """
        best_score = IMPOSSIBLE
        best_order = []
 
        # Option 1: collect nothing more, walk to the exit (+1 action for EXIT).
        walk = costs[current].get(exit_cell)
        if walk is not None and walk + 1 <= budget:
            best_score = -rate * walk
 
        # Option 2: collect one more reward first, then plan the rest the same way.
        for reward in remaining:
            walk = costs[current].get(reward.position)
            if walk is None:
                continue
            others = [other for other in remaining if other is not reward]
            rest_score, rest_order = self.best_plan(
                reward.position, others, budget - (walk + 1), costs, exit_cell, rate
            )
            score = reward.value - rate * (walk + 1) + rest_score  # +1 for COLLECT
            if score > best_score:
                best_score = score
                best_order = [reward] + rest_order
 
        return best_score, best_order
 
    def routes_from(self, state, start):
        """Return (cost to each cell, first action(s) toward each cell). Remembered."""
        key = (start, state.defeated_enemy_ids)  # only changes when an enemy is defeated
        if key not in self.memory:
            self.memory[key] = self.search(state, start)
        return self.memory[key]
 
    def search(self, state, start):
        """BFS again, but steps no longer cost the same, so the queue must give the
        CHEAPEST cell first. heapq is a "priority queue" that does exactly that."""
        enemies = self.enemies_by_cell(state)
        can_engage = WorldActionType.ENGAGE in state.allowed_actions
        watched = self.patrol_route_cells(state)
 
        cost_to = {start: 0}    # cheapest cost found so far for each cell
        first_to = {start: []}  # the first action(s) on that cheapest way
        queue = [(0, start)]    # (cost, cell): the smallest cost comes out first
 
        while len(queue) > 0:
            cost, cell = heapq.heappop(queue)
            if cost > cost_to[cell]:
                continue  # old entry: a cheaper way to this cell was found later
 
            for move, row_change, column_change in MOVES:
                neighbor = Position(cell.row + row_change, cell.column + column_change)
                if not state.is_traversable(neighbor):
                    continue
 
                if neighbor in enemies:
                    if not can_engage:
                        continue  # cannot get past this enemy
                    enemy = enemies[neighbor]
                    step_cost = 1 + enemy.encounter_penalty + 1
                    step = [
                        WorldAction(WorldActionType.ENGAGE, target_id=enemy.enemy_id),
                        WorldAction(move),
                    ]
                else:
                    step_cost = 1
                    step = [WorldAction(move)]
                if neighbor in watched:
                    step_cost += PATROL_EXTRA  # a patrol walks here: avoid if we can
 
                new_cost = cost + step_cost
                if neighbor not in cost_to or new_cost < cost_to[neighbor]:
                    cost_to[neighbor] = new_cost
                    first_to[neighbor] = step if cell == start else first_to[cell]
                    heapq.heappush(queue, (new_cost, neighbor))
 
        return cost_to, first_to
 
    def enemies_by_cell(self, state):
        """A dictionary: cell -> enemy, for STANDING enemies that are still alive."""
        patrol_ids = [patrol.enemy_id for patrol in state.level.patrols]
        enemies = {}
        for enemy in state.level.enemies:
            if enemy.enemy_id in state.defeated_enemy_ids or enemy.enemy_id in patrol_ids:
                continue
            enemies[enemy.position] = enemy
        return enemies
 
    # ---------- moving enemies (patrols) ----------
 
    def patrol_route_cells(self, state):
        """Every cell that any patrol ever walks on."""
        cells = set()
        for patrol in state.level.patrols:
            for position in patrol.positions:
                cells.add(position)
        return cells
 
    def patrol_cells(self, state):
        """Cells a patrol is on now, or will be on after our next action."""
        cells = set()
        for patrol in state.level.patrols:
            for seen in state.enemy_observations:
                if seen.enemy_id == patrol.enemy_id and seen.position is not None:
                    cells.add(seen.position)
                    if seen.phase is not None:
                        cells.add(patrol.positions[(seen.phase + 1) % patrol.period])
        return cells
 
    def cell_after(self, here, action):
        """The cell we would stand on after this action."""
        for move, row_change, column_change in MOVES:
            if action.action_type == move:
                return Position(here.row + row_change, here.column + column_change)
        return here  # COLLECT, ENGAGE, WAIT do not move us
 
    def avoid_patrols(self, state, action):
        """Keep the action if it is safe; otherwise WAIT or sidestep."""
        if action.action_type == WorldActionType.EXIT:
            return action  # EXIT does not advance the patrol clock
        danger = self.patrol_cells(state)
        here = state.agent_position
        if self.cell_after(here, action) not in danger:
            return action
 
        enemies = self.enemies_by_cell(state)
        options = [WorldAction.wait()]
        for move, row_change, column_change in MOVES:
            options.append(WorldAction(move))
        for option in options:
            cell = self.cell_after(here, option)
            if cell in danger:
                continue
            if option.action_type == WorldActionType.WAIT:
                if WorldActionType.WAIT not in state.allowed_actions:
                    continue
            elif not state.is_traversable(cell) or cell in enemies:
                continue
            return option
 
        return action  # nothing is safe, so keep the plan
 