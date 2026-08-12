"""Tests du deroulement d'un tournoi, de la creation au sacre du vainqueur."""

from django.test import TestCase

from core.http import ApiError
from game import services
from game.models import Match, Tournament


def aliases(*names) -> list[dict]:
    return [{"user": None, "alias": name} for name in names]


def finish(match: Match, *, winner_side: int, scores=(3, 1)) -> Match:
    """Simule la fin d'une rencontre sans faire tourner le moteur."""
    snapshot = {
        "scores": list(scores) if winner_side == 0 else list(reversed(scores)),
        "winner": winner_side,
    }
    stats = {"duration_seconds": 12.0, "total_hits": 9, "longest_rally": 4}
    return services.finish_match(match.pk, snapshot, stats)


class TournamentCreationTest(TestCase):
    def test_local_tournament_starts_immediately(self):
        tournament = services.create_tournament(
            name="Coupe", mode=Tournament.MODE_LOCAL, points_to_win=3,
            entries=aliases("Ada", "Bob", "Cyd", "Dov"),
        )
        self.assertEqual(tournament.state, Tournament.STATE_RUNNING)
        self.assertEqual(tournament.players.count(), 4)
        self.assertEqual(tournament.rounds_count, 2)

    def test_bracket_contains_every_round_from_the_start(self):
        tournament = services.create_tournament(
            name="Coupe", mode=Tournament.MODE_LOCAL, points_to_win=3,
            entries=aliases("Ada", "Bob", "Cyd", "Dov"),
        )
        self.assertEqual(tournament.matches.filter(round_index=0).count(), 2)
        self.assertEqual(tournament.matches.filter(round_index=1).count(), 1)
        self.assertEqual(
            tournament.matches.filter(state=Match.STATE_LOBBY).count(), 2)
        self.assertEqual(
            tournament.matches.filter(state=Match.STATE_PENDING).count(), 1)

    def test_top_seeds_receive_the_byes(self):
        tournament = services.create_tournament(
            name="Coupe", mode=Tournament.MODE_LOCAL, points_to_win=3,
            entries=aliases("Ada", "Bob", "Cyd", "Dov", "Eve"),
        )
        self.assertEqual(tournament.matches.filter(round_index=0).count(), 1)

        quarter = tournament.matches.get(round_index=0)
        self.assertEqual({quarter.alias_of(0), quarter.alias_of(1)}, {"Dov", "Eve"})

        semis = list(tournament.matches.filter(round_index=1).order_by("slot_index"))
        seated = {semis[0].alias_of(0), semis[1].alias_of(0), semis[1].alias_of(1)}
        self.assertEqual(seated, {"Ada", "Bob", "Cyd"})

    def test_a_tournament_needs_at_least_two_players(self):
        with self.assertRaises(ApiError):
            services.create_tournament(
                name="Coupe", mode=Tournament.MODE_LOCAL, points_to_win=3,
                entries=aliases("Ada"),
            )

    def test_duplicate_alias_is_rejected_by_the_database(self):
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            services.create_tournament(
                name="Coupe", mode=Tournament.MODE_LOCAL, points_to_win=3,
                entries=aliases("Ada", "Ada"),
            )


class ProgressionTest(TestCase):
    def setUp(self):
        self.tournament = services.create_tournament(
            name="Coupe", mode=Tournament.MODE_LOCAL, points_to_win=3,
            entries=aliases("Ada", "Bob", "Cyd", "Dov"),
        )

    def semis(self):
        return list(self.tournament.matches.filter(round_index=0).order_by("slot_index"))

    def final(self):
        return self.tournament.matches.get(round_index=1)

    def test_winner_moves_into_the_final(self):
        first = self.semis()[0]
        expected = first.alias_of(0)

        finish(first, winner_side=0)

        final = self.final()
        self.assertEqual(final.alias_of(0), expected)
        self.assertEqual(final.state, Match.STATE_PENDING)

    def test_loser_is_marked_eliminated(self):
        first = self.semis()[0]
        loser = first.alias_of(1)

        finish(first, winner_side=0)

        self.assertTrue(self.tournament.players.get(alias=loser).eliminated)
        self.assertFalse(self.tournament.players.get(alias=first.alias_of(0)).eliminated)

    def test_final_becomes_playable_once_both_semis_are_done(self):
        for semi in self.semis():
            finish(semi, winner_side=0)

        final = self.final()
        self.assertEqual(final.state, Match.STATE_LOBBY)
        self.assertTrue(final.is_ready)

    def test_next_match_follows_the_bracket_order(self):
        self.assertEqual(self.tournament.next_match().slot_index, 0)

        finish(self.semis()[0], winner_side=0)
        self.assertEqual(self.tournament.next_match().slot_index, 1)

        finish(self.semis()[1], winner_side=1)
        self.assertEqual(self.tournament.next_match().round_index, 1)

    def test_winning_the_final_crowns_the_champion(self):
        for semi in self.semis():
            finish(semi, winner_side=0)
        champion = self.final().alias_of(0)

        finish(self.final(), winner_side=0)

        self.tournament.refresh_from_db()
        self.assertEqual(self.tournament.state, Tournament.STATE_FINISHED)
        self.assertIsNotNone(self.tournament.winner)
        self.assertEqual(self.tournament.winner.alias, champion)
        self.assertIsNotNone(self.tournament.finished_at)

    def test_recording_the_same_result_twice_is_harmless(self):
        semi = self.semis()[0]
        finish(semi, winner_side=0)
        finish(semi, winner_side=1)

        semi.refresh_from_db()
        self.assertEqual(semi.winner_side, 0)
        self.assertEqual(self.final().alias_of(0), semi.alias_of(0))


class MatchTest(TestCase):
    def test_local_match_refuses_two_identical_aliases(self):
        with self.assertRaises(ApiError):
            services.create_local_match(alias1="Ada", alias2="ada", points_to_win=3)

    def test_stored_alias_survives_and_is_used_for_display(self):
        match = services.create_local_match(alias1="Ada", alias2="Bob", points_to_win=3)
        self.assertEqual(match.alias_of(Match.LEFT), "Ada")
        self.assertEqual(match.alias_of(Match.RIGHT), "Bob")

    def test_result_is_persisted_with_its_statistics(self):
        match = services.create_local_match(alias1="Ada", alias2="Bob", points_to_win=3)
        finish(match, winner_side=1, scores=(3, 2))

        match.refresh_from_db()
        self.assertEqual(match.state, Match.STATE_FINISHED)
        self.assertEqual(match.winner_side, 1)
        self.assertEqual(match.longest_rally, 4)
        self.assertIsNotNone(match.finished_at)
