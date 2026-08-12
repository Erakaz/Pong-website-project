"""Agregats statistiques sur les matchs."""

from __future__ import annotations

from django.db.models import Q, QuerySet

from game.models import Match


def finished_matches(user) -> QuerySet[Match]:
    """Parties terminees auxquelles ce compte a reellement participe."""
    return (Match.objects
            .filter(Q(player1=user) | Q(player2=user), state=Match.STATE_FINISHED)
            .select_related("player1", "player2", "tournament")
            .order_by("-finished_at"))


def summary(user) -> dict:
    """Bilan chiffre d'un joueur."""
    wins = losses = 0
    points_for = points_against = 0
    longest_rally = 0
    total_seconds = 0.0

    matches = list(finished_matches(user))
    for match in matches:
        side = match.side_of_user(user)
        if side is None:
            continue
        own, other = (match.score1, match.score2) if side == Match.LEFT \
            else (match.score2, match.score1)
        points_for += own
        points_against += other
        longest_rally = max(longest_rally, match.longest_rally)
        total_seconds += match.duration_seconds
        if match.winner_side == side:
            wins += 1
        else:
            losses += 1

    played = wins + losses
    return {
        "played": played,
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / played * 100, 1) if played else 0.0,
        "points_for": points_for,
        "points_against": points_against,
        "points_diff": points_for - points_against,
        "longest_rally": longest_rally,
        "playtime_seconds": round(total_seconds),
        "current_streak": _streak(matches, user),
    }


def _streak(matches: list[Match], user) -> dict:
    """Serie en cours : nombre de victoires (ou defaites) consecutives."""
    streak = 0
    kind = None
    for match in matches:
        side = match.side_of_user(user)
        if side is None:
            continue
        outcome = "win" if match.winner_side == side else "loss"
        if kind is None:
            kind = outcome
        elif outcome != kind:
            break
        streak += 1
    return {"type": kind, "count": streak}


def by_opponent(user, limit: int = 8) -> list[dict]:
    """Bilan adversaire par adversaire, du plus frequent au moins frequent."""
    tally: dict[str, dict] = {}
    for match in finished_matches(user):
        side = match.side_of_user(user)
        if side is None:
            continue
        opponent = match.alias_of(1 - side) or "Inconnu"
        entry = tally.setdefault(opponent, {"opponent": opponent, "wins": 0, "losses": 0})
        if match.winner_side == side:
            entry["wins"] += 1
        else:
            entry["losses"] += 1

    rows = sorted(tally.values(), key=lambda row: row["wins"] + row["losses"], reverse=True)
    for row in rows:
        played = row["wins"] + row["losses"]
        row["played"] = played
        row["win_rate"] = round(row["wins"] / played * 100, 1) if played else 0.0
    return rows[:limit]


def recent_form(user, limit: int = 12) -> list[dict]:
    """Les N derniers resultats, du plus ancien au plus recent."""
    entries = []
    for match in list(finished_matches(user)[:limit])[::-1]:
        side = match.side_of_user(user)
        if side is None:
            continue
        own, other = (match.score1, match.score2) if side == Match.LEFT \
            else (match.score2, match.score1)
        entries.append({
            "id": str(match.id),
            "opponent": match.alias_of(1 - side),
            "for": own,
            "against": other,
            "won": match.winner_side == side,
            "played_at": match.finished_at.isoformat() if match.finished_at else None,
        })
    return entries


def match_detail(match: Match) -> dict:
    """Tableau de bord d'une partie : deroule du score, point par point."""
    timeline = []
    running = [0, 0]
    for point in match.points_log or []:
        side = point.get("side")
        if side not in (0, 1):
            continue
        running[side] += 1
        timeline.append({
            "t": point.get("t", 0),
            "side": side,
            "rally": point.get("rally", 0),
            "scores": list(running),
        })

    rallies = [point["rally"] for point in timeline] or [0]
    return {
        "match": match.to_dict(),
        "timeline": timeline,
        "summary": {
            "duration_seconds": match.duration_seconds,
            "total_hits": match.total_hits,
            "longest_rally": match.longest_rally,
            "average_rally": round(sum(rallies) / len(rallies), 1),
            "points_played": len(timeline),
        },
    }


def history(user, limit: int = 20) -> list[dict]:
    """Historique des rencontres, vu du cote de ce joueur."""
    entries = []
    for match in finished_matches(user)[:limit]:
        side = match.side_of_user(user)
        if side is None:
            continue
        opponent_side = 1 - side
        own, other = (match.score1, match.score2) if side == Match.LEFT \
            else (match.score2, match.score1)
        entries.append({
            "id": str(match.id),
            "opponent": match.alias_of(opponent_side),
            "opponent_id": match.user_of(opponent_side).pk
            if match.user_of(opponent_side) else None,
            "score": [own, other],
            "won": match.winner_side == side,
            "by_forfeit": match.by_forfeit,
            "mode": match.mode,
            "tournament": match.tournament.name if match.tournament_id else None,
            "tournament_id": str(match.tournament_id) if match.tournament_id else None,
            "duration_seconds": match.duration_seconds,
            "longest_rally": match.longest_rally,
            "played_at": match.finished_at.isoformat() if match.finished_at else None,
        })
    return entries
