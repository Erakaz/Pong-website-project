"""Generation et progression du tableau de tournoi (elimination directe)."""

from __future__ import annotations

MIN_PLAYERS = 2
MAX_PLAYERS = 16


def bracket_size(player_count: int) -> int:
    """Plus petite puissance de deux pouvant accueillir tous les joueurs."""
    if player_count < MIN_PLAYERS:
        raise ValueError("Un tournoi demande au moins deux joueurs.")
    size = 1
    while size < player_count:
        size *= 2
    return size


def rounds_count(player_count: int) -> int:
    return bracket_size(player_count).bit_length() - 1


def seed_order(size: int) -> list[int]:
    """Ordre des tetes de serie dans le tableau."""
    order = [0]
    while len(order) < size:
        total = len(order) * 2
        order = [value for index in order for value in (index, total - 1 - index)]
    return order


def first_round_pairings(player_count: int) -> list[tuple[int, int | None]]:
    """Rencontres du premier tour, en indices de tete de serie."""
    size = bracket_size(player_count)
    slots = [index if index < player_count else None for index in seed_order(size)]
    return [(slots[i], slots[i + 1]) for i in range(0, size, 2)]


def parent_slot(round_index: int, slot_index: int) -> tuple[int, int]:
    """Emplacement du match ou se qualifie le vainqueur d'un match donne."""
    return round_index + 1, slot_index // 2


def parent_side(slot_index: int) -> int:
    """Cote occupe par le qualifie dans le match suivant (0 = gauche)."""
    return slot_index % 2


def describe(player_count: int) -> dict:
    """Resume du tableau, utile aux tests et a la documentation."""
    size = bracket_size(player_count)
    return {
        "players": player_count,
        "bracket_size": size,
        "rounds": rounds_count(player_count),
        "byes": size - player_count,
        "first_round": first_round_pairings(player_count),
    }
