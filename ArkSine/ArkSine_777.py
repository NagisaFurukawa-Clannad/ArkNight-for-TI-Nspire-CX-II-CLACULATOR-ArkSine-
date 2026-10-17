"""ArkSine: a compact winding-path defense game for TI-Nspire Python."""

import time

try:
    import ti_draw
except ImportError:
    ti_draw = None

try:
    import ti_system
except ImportError:
    ti_system = None


class GameExit(Exception):
    """Signal that the player requested to quit."""


TILE_SIZE = 20
MAP_X = 30
MAP_Y = 42
GRID_ROWS = 6
GRID_COLS = 13

PATH = [
    (0, 12), (0, 11), (0, 10), (0, 9), (0, 8),
    (0, 7), (0, 6), (0, 5), (0, 4), (0, 3), (0, 2),
    (1, 2), (2, 2), (2, 3), (2, 4), (2, 5), (2, 6),
    (2, 7), (2, 8), (2, 9), (2, 10), (2, 11),
    (3, 11), (4, 11), (4, 10), (4, 9), (4, 8),
    (4, 7), (4, 6), (4, 5), (4, 4), (4, 3),
    (4, 2), (4, 1), (4, 0), (5, 0)
]

ROAD_BRANCHES = [
    [(3, 12)],
    [(5, 6)]
]

SECOND_BASE_ROUTE = ((1, 2), [(1, 1)], (1, 0))

SHORTCUT_ROUTES = [
    ((0, 6), [(1, 6)], (2, 6)),
    ((2, 10), [(3, 10)], (4, 10))
]

ROAD_TILES = set(PATH)
for branch in ROAD_BRANCHES:
    ROAD_TILES.update(branch)
for start, tiles, end in SHORTCUT_ROUTES:
    ROAD_TILES.update(tiles)
ROAD_TILES.update(SECOND_BASE_ROUTE[1])

ROAD_PATH = PATH[:]
for start, tiles, end in SHORTCUT_ROUTES:
    ROAD_PATH.extend(tiles)
ROAD_PATH.extend(SECOND_BASE_ROUTE[1])
ROAD_PATH.append(SECOND_BASE_ROUTE[2])
ROAD_INDEX_BY_TILE = {}
for index in range(len(ROAD_PATH)):
    ROAD_INDEX_BY_TILE[ROAD_PATH[index]] = index
BASE_PATH_INDICES = [
    ROAD_INDEX_BY_TILE[PATH[-1]],
    ROAD_INDEX_BY_TILE[SECOND_BASE_ROUTE[2]]
]
BASE_INDEX_TO_SLOT = {BASE_PATH_INDICES[index]: index
                      for index in range(len(BASE_PATH_INDICES))}
DEPLOYABLE_ROAD_INDICES = [
    index for index in range(len(ROAD_PATH))
    if index not in BASE_INDEX_TO_SLOT
]

NEXT_PATH_OPTIONS = {}
for index in range(len(PATH) - 1):
    NEXT_PATH_OPTIONS[index] = [index + 1]
for start, tiles, end in SHORTCUT_ROUTES:
    route = [start] + tiles + [end]
    start_index = ROAD_INDEX_BY_TILE[start]
    shortcut_index = ROAD_INDEX_BY_TILE[tiles[0]]
    NEXT_PATH_OPTIONS[start_index].append(shortcut_index)
    for index in range(1, len(route) - 1):
        NEXT_PATH_OPTIONS[ROAD_INDEX_BY_TILE[route[index]]] = [
            ROAD_INDEX_BY_TILE[route[index + 1]]
        ]
start, tiles, end = SECOND_BASE_ROUTE
route = [start] + tiles + [end]
NEXT_PATH_OPTIONS[ROAD_INDEX_BY_TILE[start]].append(
    ROAD_INDEX_BY_TILE[tiles[0]])
for index in range(1, len(route) - 1):
    NEXT_PATH_OPTIONS[ROAD_INDEX_BY_TILE[route[index]]] = [
        ROAD_INDEX_BY_TILE[route[index + 1]]
    ]

ROAD_NEIGHBORS = {}
for start_index, next_indices in NEXT_PATH_OPTIONS.items():
    for next_index in next_indices:
        ROAD_NEIGHBORS.setdefault(start_index, []).append(next_index)
        ROAD_NEIGHBORS.setdefault(next_index, []).append(start_index)

SLOTS = [
    (34, 3, 0),
    (23, 5, 12),
    (30, 5, 4),
    (26, 5, 8)
]

SNIPER_SITES = [
    (15, 1, 5),
    (18, 1, 8),
    (29, 3, 5),
    (26, 3, 8)
]

MOVE_INTERVAL = 2.0
POLL_INTERVAL = 0.05
SPAWN_INTERVAL = MOVE_INTERVAL * 3
ENEMY_HP = 4
ENEMY_ATTACK = 1
ASSAULT_HP = 7
DEFENSE_HP = 9
ASSAULT_BLOCK = 1
DEFENSE_BLOCK = 3


def deployment_count():
    return len(SLOTS) + len(SNIPER_SITES) + len(DEPLOYABLE_ROAD_INDICES)


def tile_center(row, col):
    """Return the screen center of a map tile."""
    return (MAP_X + col * TILE_SIZE + TILE_SIZE // 2,
            MAP_Y + row * TILE_SIZE + TILE_SIZE // 2)


def deploy_point(index):
    """Return kind, local index, row, column, and path index."""
    if index < len(SLOTS):
        path_index, row, col = SLOTS[index]
        return ("pad", index, row, col, path_index)
    index -= len(SLOTS)
    if index < len(SNIPER_SITES):
        path_index, row, col = SNIPER_SITES[index]
        return ("sniper", index, row, col, path_index)
    road_slot = index - len(SNIPER_SITES)
    path_index = DEPLOYABLE_ROAD_INDICES[road_slot]
    row, col = ROAD_PATH[path_index]
    return ("road", road_slot, row, col, path_index)


def operator_path_index(slot):
    if slot < len(SLOTS):
        return SLOTS[slot][0]
    return SNIPER_SITES[slot - len(SLOTS)][0]


def road_tile_occupied(road_units, path_index):
    return any(unit[0] == path_index for unit in road_units)


def distance_to_base(path_index, blocked_paths):
    """Find the shortest forward route to the base without blocked tiles."""
    frontier = [(path_index, 0)]
    visited = {path_index}
    while frontier:
        current, distance = frontier.pop(0)
        if current in BASE_INDEX_TO_SLOT:
            return distance
        for next_index in NEXT_PATH_OPTIONS.get(current, []):
            if next_index in blocked_paths or next_index in visited:
                continue
            visited.add(next_index)
            frontier.append((next_index, distance + 1))
    return None


def next_path_index(path_index, enemy_id, blocked_paths=None):
    """Choose the shortest unblocked route, falling back if all routes block."""
    if blocked_paths is None:
        blocked_paths = set()
    options = NEXT_PATH_OPTIONS.get(path_index, [])
    if not options:
        return path_index
    available = []
    for next_index in options:
        if next_index in blocked_paths:
            continue
        distance = distance_to_base(next_index, blocked_paths)
        if distance is not None:
            available.append((distance, next_index))
    if available:
        shortest = min(route[0] for route in available)
        shortest_options = [route[1] for route in available
                            if route[0] == shortest]
        return shortest_options[enemy_id % len(shortest_options)]

    fallback = []
    for next_index in options:
        distance = distance_to_base(next_index, set())
        if distance is not None:
            fallback.append((distance, next_index))
    if not fallback:
        return path_index
    shortest = min(route[0] for route in fallback)
    shortest_options = [route[1] for route in fallback
                        if route[0] == shortest]
    return shortest_options[enemy_id % len(shortest_options)]


def enemy_route_edges(path_index, enemy_id, blocked_paths):
    """Return the chosen route from an enemy's tile to the base."""
    edges = []
    visited = {path_index}
    current = path_index
    while current not in BASE_INDEX_TO_SLOT:
        next_index = next_path_index(current, enemy_id, blocked_paths)
        if next_index == current or next_index in visited:
            break
        edges.append((current, next_index))
        visited.add(next_index)
        current = next_index
    return edges


def road_distance(start, end):
    """Return the shortest distance between two tiles on the road network."""
    if start == end:
        return 0
    visited = {start}
    frontier = [start]
    distance = 0
    while frontier:
        distance += 1
        next_frontier = []
        for current in frontier:
            for neighbor in ROAD_NEIGHBORS.get(current, []):
                if neighbor == end:
                    return distance
                if neighbor not in visited:
                    visited.add(neighbor)
                    next_frontier.append(neighbor)
        frontier = next_frontier
    return len(ROAD_PATH)


def read_number(prompt, low, high):
    """Read an integer in the given range."""
    if ti_system is not None and hasattr(ti_system, "get_key"):
        print(prompt, end="")
        while True:
            key = ti_system.get_key()
            if key == "esc":
                raise GameExit()
            if key in ("0", "1", "2", "3", "4", "5", "6", "7", "8", "9"):
                value = int(key)
                if low <= value <= high:
                    print(key)
                    return value
        return

    while True:
        try:
            value = int(input(prompt))
        except ValueError:
            print("Please enter a number.")
            continue
        if low <= value <= high:
            return value
        print("Choose a number from", low, "to", high)


def show_status(units, enemies, energy, base_hp, round_number,
                road_units=None):
    print("")
    print("Round", round_number, " Energy:", energy,
          " Bases:", base_hp[0], "/", base_hp[1])
    print("Enemies on route:", len(enemies))
    for index in range(len(SLOTS) + len(SNIPER_SITES)):
        operator = units[index]
        if operator is None:
            print("Position", index + 1, "- empty")
        else:
            print("Position", index + 1, "-", operator[0],
                  "HP:", operator[4], "/", operator[5])
    if road_units is not None:
        for unit in road_units:
            print(unit[1], "on road tile", unit[0] + 1, "HP:", unit[2])


def move_selected_slot(selected, direction):
    """Move selection to the nearest pad in the requested direction."""
    point = deploy_point(selected)
    x, y = tile_center(point[2], point[3])
    best_slot = selected
    best_score = None

    for index in range(deployment_count()):
        if index == selected:
            continue
        other_point = deploy_point(index)
        other_x, other_y = tile_center(other_point[2], other_point[3])
        dx = other_x - x
        dy = other_y - y
        if direction == "left" and dx < 0:
            primary, cross = -dx, abs(dy)
        elif direction == "right" and dx > 0:
            primary, cross = dx, abs(dy)
        elif direction == "up" and dy < 0:
            primary, cross = -dy, abs(dx)
        elif direction == "down" and dy > 0:
            primary, cross = dy, abs(dx)
        else:
            continue
        score = primary + cross * 2
        if best_score is None or score < best_score:
            best_slot = index
            best_score = score
    return best_slot


def draw_board(units, enemies, energy, base_hp, round_number, message,
               selected_slot=None, road_units=None):
    if ti_draw is None:
        return
    if road_units is None:
        road_units = []

    ti_draw.clear()
    ti_draw.set_color(15, 25, 43)
    ti_draw.fill_rect(0, 0, 320, 210)
    ti_draw.set_color(218, 228, 239)
    ti_draw.draw_text(8, 5, "ARKSINE  STAGE 1-" + str(round_number))
    ti_draw.draw_text(8, 21, "ENERGY " + str(energy))
    ti_draw.draw_text(152, 21, "B1 " + str(base_hp[0]) +
                      " B2 " + str(base_hp[1]))
    slot_by_tile = {}
    for slot in range(len(SLOTS)):
        row, col = SLOTS[slot][1], SLOTS[slot][2]
        slot_by_tile[(row, col)] = slot
    for index in range(len(SNIPER_SITES)):
        row, col = SNIPER_SITES[index][1], SNIPER_SITES[index][2]
        slot_by_tile[(row, col)] = len(SLOTS) + index
    selected_point = None
    if selected_slot is not None and 0 <= selected_slot < deployment_count():
        selected_point = deploy_point(selected_slot)
    for row in range(GRID_ROWS):
        for col in range(GRID_COLS):
            x = MAP_X + col * TILE_SIZE
            y = MAP_Y + row * TILE_SIZE
            tile = (row, col)
            if tile == PATH[0]:
                ti_draw.set_color(165, 48, 55)
            elif tile in (PATH[-1], SECOND_BASE_ROUTE[2]):
                ti_draw.set_color(41, 122, 76)
            elif tile in ROAD_TILES:
                ti_draw.set_color(111, 132, 153)
            elif tile in slot_by_tile:
                slot = slot_by_tile[tile]
                if slot == selected_slot:
                    ti_draw.set_color(226, 203, 116)
                else:
                    if slot >= len(SLOTS):
                        ti_draw.set_color(53, 111, 119)
                    else:
                        ti_draw.set_color(67, 91, 116)
            else:
                ti_draw.set_color(25, 39, 59)
            if selected_point is not None and selected_point[2:4] == tile:
                ti_draw.set_color(226, 203, 116)
            ti_draw.fill_rect(x, y, TILE_SIZE - 1, TILE_SIZE - 1)

    occupied_paths = set(unit[0] for unit in road_units)
    route_edges = set()
    for enemy in enemies:
        route_edges.update(enemy_route_edges(
            enemy[0], enemy[2], occupied_paths))
    ti_draw.set_color(194, 55, 61)
    for start_index, next_index in route_edges:
        start_x, start_y = tile_center(*ROAD_PATH[start_index])
        end_x, end_y = tile_center(*ROAD_PATH[next_index])
        ti_draw.draw_line(start_x, start_y, end_x, end_y)

    for row in range(GRID_ROWS):
        for col in range(GRID_COLS):
            tile = (row, col)
            center_x, center_y = tile_center(row, col)
            if tile in slot_by_tile:
                slot = slot_by_tile[tile]
                operator = units[slot]
                if operator is None:
                    if slot >= len(SLOTS):
                        ti_draw.set_color(110, 220, 220)
                        mark = "S"
                    else:
                        ti_draw.set_color(223, 231, 239)
                        mark = str(slot + 1)
                    ti_draw.draw_text(center_x - 3, center_y - 5, mark)
                else:
                    if operator[0] == "Guard":
                        ti_draw.set_color(44, 123, 220)
                        mark = "G"
                    elif operator[0] == "Sniper":
                        ti_draw.set_color(42, 173, 132)
                        mark = "S"
                    else:
                        ti_draw.set_color(159, 91, 206)
                        mark = "C"
                    ti_draw.fill_circle(center_x, center_y, 8)
                    ti_draw.set_color(255, 255, 255)
                    ti_draw.draw_text(center_x - 3, center_y - 5, mark)
                    ti_draw.draw_text(center_x - 3, center_y + 4,
                                      str(operator[4]))
            if tile in ROAD_TILES:
                tile_units = [unit for unit in road_units
                              if ROAD_PATH[unit[0]] == tile]
                for road_unit in tile_units:
                    if road_unit[1] == "A":
                        ti_draw.set_color(224, 125, 67)
                    else:
                        ti_draw.set_color(54, 177, 194)
                    ti_draw.fill_circle(center_x, center_y, 7)
                    ti_draw.set_color(14, 35, 48)
                    ti_draw.draw_text(center_x - 3, center_y - 5,
                                      road_unit[1])

    base_x, base_y = tile_center(5, 0)
    ti_draw.set_color(112, 207, 128)
    ti_draw.fill_circle(base_x, base_y, 6)
    ti_draw.set_color(19, 72, 42)
    ti_draw.draw_text(base_x - 3, base_y - 5, "B")

    second_base_x, second_base_y = tile_center(*SECOND_BASE_ROUTE[2])
    ti_draw.set_color(112, 207, 128)
    ti_draw.fill_circle(second_base_x, second_base_y, 6)
    ti_draw.set_color(19, 72, 42)
    ti_draw.draw_text(second_base_x - 3, second_base_y - 5, "2")

    entry_x, entry_y = tile_center(0, 12)
    ti_draw.set_color(255, 226, 220)
    ti_draw.draw_text(entry_x - 3, entry_y - 5, "I")

    for enemy in enemies:
        row, col = ROAD_PATH[enemy[0]]
        x, y = tile_center(row, col)
        ti_draw.set_color(82, 33, 35)
        ti_draw.fill_circle(x, y, 8)
        ti_draw.set_color(205, 63, 55)
        ti_draw.fill_circle(x, y - 1, 7)
        ti_draw.set_color(255, 228, 193)
        ti_draw.fill_circle(x + 2, y - 3, 2)
        ti_draw.draw_text(x - 3, y + 4, str(enemy[1]))

    ti_draw.set_color(218, 228, 239)
    ti_draw.draw_text(8, 169, "5=ASSAULT 6=DEFENSE (ROAD)")
    ti_draw.draw_text(8, 183, "7=GUARD 8=SNIPER 9=CASTER (PAD)")
    if message.startswith("VICTORY"):
        ti_draw.set_color(112, 207, 128)
        ti_draw.draw_text(127, 103, "VICTORY")
    elif message.startswith("GAME OVER"):
        ti_draw.set_color(205, 63, 55)
        ti_draw.draw_text(136, 103, "DEFEAT")


def advance_tick(units, road_units, enemies, base_hp):
    """Resolve attacks, road combat, and movement for one game tick."""
    enemies = [enemy for enemy in enemies if enemy[1] > 0]
    blocked_enemy_ids = []
    for road_unit in road_units:
        block_capacity = (ASSAULT_BLOCK if road_unit[1] == "A"
                          else DEFENSE_BLOCK)
        blocked_count = 0
        for enemy in enemies:
            if enemy[0] == road_unit[0] and enemy[2] not in blocked_enemy_ids:
                blocked_enemy_ids.append(enemy[2])
                blocked_count += 1
                if blocked_count == block_capacity:
                    break
        road_unit[2] -= blocked_count * ENEMY_ATTACK
    road_units[:] = [unit for unit in road_units if unit[2] > 0]
    attack_operators(units, enemies, blocked_enemy_ids)

    for slot in range(len(units)):
        operator = units[slot]
        if operator is None:
            continue
        target = None
        slot_path_index = operator_path_index(slot)
        target_distance = None
        for enemy in enemies:
            distance = road_distance(enemy[0], slot_path_index)
            if enemy[1] > 0 and distance <= operator[3]:
                if target is None or distance < target_distance:
                    target = enemy
                    target_distance = distance
        if target is not None:
            target[1] -= operator[2]

    for road_unit in road_units:
        unit_path = road_unit[0]
        unit_role = road_unit[1]
        unit_damage = 3 if unit_role == "A" else 2
        unit_range = 1 if unit_role == "A" else 0
        target = None
        target_distance = None
        for enemy in enemies:
            distance = road_distance(enemy[0], unit_path)
            if enemy[1] <= 0 or distance > unit_range:
                continue
            if target is None or distance < target_distance:
                target = enemy
                target_distance = distance
        if target is not None:
            target[1] -= unit_damage

    enemies = [enemy for enemy in enemies if enemy[1] > 0]
    occupied_paths = set(unit[0] for unit in road_units)
    living_enemies = []
    for enemy in enemies:
        if enemy[2] not in blocked_enemy_ids:
            enemy[0] = next_path_index(
                enemy[0], enemy[2], occupied_paths)
        if enemy[0] in BASE_INDEX_TO_SLOT:
            base_slot = BASE_INDEX_TO_SLOT[enemy[0]]
            base_hp[base_slot] -= 1
            print("Enemy", enemy[2], "reaches base", base_slot + 1, "!")
        else:
            living_enemies.append(enemy)
    return living_enemies, base_hp


def attack_operators(units, enemies, blocked_enemy_ids=()):
    """Let unblocked enemies attack the nearest operator within one road tile."""
    for enemy in enemies:
        if enemy[1] <= 0 or enemy[2] in blocked_enemy_ids:
            continue
        target_slot = None
        target_distance = None
        for slot, operator in enumerate(units):
            if operator is None:
                continue
            distance = road_distance(enemy[0], operator_path_index(slot))
            if distance <= 1 and (
                    target_slot is None or distance < target_distance):
                target_slot = slot
                target_distance = distance
        if target_slot is None:
            continue
        operator = units[target_slot]
        operator[4] -= ENEMY_ATTACK
        if operator[4] <= 0:
            print("Enemy", enemy[2], "defeats", operator[0],
                  "at position", target_slot + 1, "!")
            units[target_slot] = None
        else:
            print("Enemy", enemy[2], "hits", operator[0],
                  "at position", target_slot + 1,
                  "- HP:", operator[4])


def realtime_main():
    """Run the calculator game with timed enemy movement and key polling."""
    unit_types = [
        ("Guard", 2, 2, 1, 6, 6),
        ("Sniper", 4, 3, 3, 5, 5),
        ("Caster", 5, 4, 2, 5, 5)
    ]
    units = [None] * (len(SLOTS) + len(SNIPER_SITES))
    road_units = []
    enemies = [[0, ENEMY_HP, 1]]
    energy = 5
    base_hp = [3, 3]
    selected_slot = 0
    spawned = 1
    move_ticks = 0
    next_move = time.time() + MOVE_INTERVAL
    next_spawn = time.time() + SPAWN_INTERVAL
    last_key = ""
    message = "5 ASSAULT  6 DEFENSE  7/8/9 PAD"

    print("Use arrows to select a road tile, operator pad or sniper site.")
    print("5 deploys an assault unit (6 HP); 6 a defense unit (8 HP).")
    print("Blocked enemies deal 1 damage each to road units.")
    print("Unblocked enemies attack operators on or next to their road tile.")
    print("Assault blocks 1 enemy; defense blocks 3. Blocked enemies attack.")
    print("7/8/9: deploy operators on empty pads.")
    print("8: sniper can also deploy on marked central sniper sites.")
    print("Road units fight and can be defeated.")
    print("20 enemies; one moves every 2 seconds and spawns every 6 seconds.")
    print("Enemies choose the shortest open route and avoid blocked tiles.")
    draw_board(units, enemies, energy, base_hp, 1, message,
               selected_slot, road_units)

    while base_hp[0] > 0 and base_hp[1] > 0:
        now = time.time()
        key = ti_system.get_key()
        if key == "esc":
            raise GameExit()
        if key and key != last_key:
            last_key = key
            if key in ("left", "right", "up", "down"):
                selected_slot = move_selected_slot(selected_slot, key)
                point = deploy_point(selected_slot)
                message = "ROAD TILE " + str(point[4] + 1) if (
                    point[0] == "road") else (
                    "SNIPER SITE" if point[0] == "sniper" else
                    "BUILD PAD " + str(point[1] + 1))
                draw_board(units, enemies, energy, base_hp,
                           move_ticks + 1, message, selected_slot,
                           road_units)
            elif key in ("5", "6"):
                point = deploy_point(selected_slot)
                if point[0] != "road":
                    message = "SELECT A ROAD TILE"
                else:
                    role = "A" if key == "5" else "D"
                    cost = 3 if role == "A" else 4
                    hp = ASSAULT_HP if role == "A" else DEFENSE_HP
                    if road_tile_occupied(road_units, point[4]):
                        message = "ROAD TILE OCCUPIED"
                    elif energy < cost:
                        message = "NOT ENOUGH ENERGY"
                    else:
                        energy -= cost
                        road_units.append([point[4], role, hp])
                        message = role + " DEPLOYED - HP " + str(hp)
                        print(role, "deployed on road tile", point[4] + 1,
                              "with", hp, "HP.")
                draw_board(units, enemies, energy, base_hp,
                           move_ticks + 1, message, selected_slot,
                           road_units)
            elif key in ("7", "8", "9"):
                point = deploy_point(selected_slot)
                if point[0] == "road":
                    message = "OPERATORS NEED A BUILDABLE PAD"
                elif point[0] == "sniper" and key != "8":
                    message = "SNIPER SITES ONLY ALLOW 8"
                else:
                    operator = unit_types[int(key) - 7]
                    slot = point[1]
                    if point[0] == "sniper":
                        slot += len(SLOTS)
                    if units[slot] is not None:
                        message = "PAD OCCUPIED"
                    elif energy < operator[1]:
                        message = "NOT ENOUGH ENERGY"
                    else:
                        energy -= operator[1]
                        units[slot] = list(operator)
                        message = operator[0].upper() + " DEPLOYED"
                        print(operator[0], "deployed on pad", slot + 1)
                draw_board(units, enemies, energy, base_hp,
                           move_ticks + 1, message, selected_slot,
                           road_units)
        elif not key:
            last_key = ""

        while (now >= next_move and base_hp[0] > 0 and
               base_hp[1] > 0):
            move_ticks += 1
            energy += 1
            enemies, base_hp = advance_tick(
                units, road_units, enemies, base_hp)
            next_move += MOVE_INTERVAL
            message = "MOVE " + str(move_ticks) + "  UNITS " + str(
                len(road_units))
            draw_board(units, enemies, energy, base_hp,
                       move_ticks + 1, message, selected_slot,
                       road_units)

        if spawned < MAX_ENEMIES and now >= next_spawn:
            spawned += 1
            enemies.append([0, ENEMY_HP, spawned])
            next_spawn += SPAWN_INTERVAL
            message = "ENEMY " + str(spawned) + " ENTERS"
            draw_board(units, enemies, energy, base_hp,
                       move_ticks + 1, message, selected_slot,
                       road_units)

        if spawned >= MAX_ENEMIES and not enemies:
            message = "VICTORY - BASE DEFENDED"
            draw_board(units, enemies, energy, base_hp,
                       move_ticks + 1, message, selected_slot,
                       road_units)
            print("VICTORY - the base is safe!")
            return
        time.sleep(POLL_INTERVAL)

    draw_board(units, enemies, energy, base_hp, move_ticks + 1,
               "GAME OVER - BASE FALLEN", selected_slot, road_units)
    print("GAME OVER - the base has fallen.")


def desktop_main():
    unit_types = [
        ("Guard", 2, 2, 1, 6, 6),
        ("Sniper", 4, 3, 3, 5, 5),
        ("Caster", 5, 4, 2, 5, 5)
    ]
    units = [None] * (len(SLOTS) + len(SNIPER_SITES))
    enemies = []
    energy = 5
    base_hp = [3, 3]
    round_number = 1
    next_enemy_id = 1

    print("ARKSINE - WINDING ROAD")
    print("Defend the base at the end of the winding road.")
    print("Use arrows to select a pad.")
    print("Press 7 Guard, 8 Sniper, 9 Caster to deploy.")
    print("Press ENTER to finish deployment.")
    print("Snipers have the longest attack range.")
    print("Press ESC at any prompt to quit.")
    print("You lose if 3 enemies reach the base.")

    while round_number <= 8 or len(enemies) > 0:
        energy += 2
        show_status(units, enemies, energy, base_hp, round_number)

        draw_board(units, enemies, energy, base_hp, round_number,
                   "7/8/9 DEPLOY  0 WAIT")
        print("1 Deploy   0 Wait")
        choice = read_number("> ", 0, 1)
        if choice == 1:
            operator_type = read_number("Operator (7-9): ", 7, 9) - 7
            slot = read_number(
                "Deploy position (1-10): ", 1,
                len(SLOTS) + len(SNIPER_SITES)) - 1
            operator = unit_types[operator_type]
            point = deploy_point(slot)
            if point[0] == "sniper" and operator_type != 1:
                print("Sniper sites only allow the Sniper operator.")
            elif units[slot] is not None:
                print("That pad is occupied. Turn skipped.")
            elif energy < operator[1]:
                print("Not enough energy. Turn skipped.")
            else:
                energy -= operator[1]
                units[slot] = list(operator)
                print(operator[0], "deployed on pad", slot + 1)

        if round_number <= 8:
            enemies.append([0, ENEMY_HP, next_enemy_id])
            print("Enemy", next_enemy_id, "enters the road.")
            next_enemy_id += 1

        attack_operators(units, enemies)
        for slot in range(len(units)):
            operator = units[slot]
            if operator is None:
                continue
            target = None
            slot_path_index = operator_path_index(slot)
            target_distance = None
            for enemy in enemies:
                distance = road_distance(enemy[0], slot_path_index)
                if enemy[1] > 0 and distance <= operator[3]:
                    if target is None or distance < target_distance:
                        target = enemy
                        target_distance = distance
            if target is not None:
                target[1] -= operator[2]
                print(operator[0], "hits enemy", target[2],
                      "- HP:", max(0, target[1]))

        living_enemies = []
        for enemy in enemies:
            if enemy[1] > 0:
                enemy[0] = next_path_index(enemy[0], enemy[2])
                if enemy[0] in BASE_INDEX_TO_SLOT:
                    base_slot = BASE_INDEX_TO_SLOT[enemy[0]]
                    base_hp[base_slot] -= 1
                    print("Enemy", enemy[2], "reaches base",
                          base_slot + 1, "!")
                else:
                    living_enemies.append(enemy)
        enemies = living_enemies

        if base_hp[0] <= 0 or base_hp[1] <= 0:
            draw_board(units, enemies, energy, base_hp, round_number,
                       "GAME OVER - BASE FALLEN")
            print("")
            print("GAME OVER - the base has fallen.")
            return

        round_number += 1

    draw_board(units, enemies, energy, base_hp, round_number - 1,
               "VICTORY - BASE DEFENDED")
    print("")
    print("VICTORY - the base is safe!")


def main():
    if ti_system is not None and hasattr(ti_system, "get_key"):
        realtime_main()
    else:
        desktop_main()


def start_game():
    try:
        main()
    except GameExit:
        print("")
        print("Game ended.")


if __name__ == "__main__":
    start_game()
elif ti_draw is not None and ti_system is not None:
    start_game()
