"""Presence en ligne."""

from __future__ import annotations

_connections: dict[int, int] = {}


def connect(user_id: int) -> bool:
    """Signale une nouvelle socket. Retourne True si l'utilisateur vient de"""
    previous = _connections.get(user_id, 0)
    _connections[user_id] = previous + 1
    return previous == 0


def disconnect(user_id: int) -> bool:
    """Signale une fermeture. Retourne True si l'utilisateur passe hors ligne."""
    remaining = _connections.get(user_id, 0) - 1
    if remaining > 0:
        _connections[user_id] = remaining
        return False
    _connections.pop(user_id, None)
    return True


def is_online(user_id: int) -> bool:
    return user_id in _connections


def filter_online(user_ids) -> set[int]:
    return {user_id for user_id in user_ids if user_id in _connections}


def online_count() -> int:
    return len(_connections)


def reset() -> None:
    """Vide le registre. Utilise par les tests pour repartir d'un etat propre."""
    _connections.clear()
