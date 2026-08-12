"""Tests du tableau de tournoi — fonctions pures, sans base de donnees."""

import unittest

from game import bracket


class BracketSizeTest(unittest.TestCase):
    def test_exact_powers_of_two(self):
        for count in (2, 4, 8, 16):
            self.assertEqual(bracket.bracket_size(count), count)

    def test_rounds_up_to_the_next_power_of_two(self):
        self.assertEqual(bracket.bracket_size(3), 4)
        self.assertEqual(bracket.bracket_size(5), 8)
        self.assertEqual(bracket.bracket_size(9), 16)

    def test_refuses_a_tournament_with_fewer_than_two_players(self):
        for count in (0, 1):
            with self.assertRaises(ValueError):
                bracket.bracket_size(count)

    def test_rounds_count(self):
        self.assertEqual(bracket.rounds_count(2), 1)
        self.assertEqual(bracket.rounds_count(4), 2)
        self.assertEqual(bracket.rounds_count(5), 3)
        self.assertEqual(bracket.rounds_count(16), 4)


class SeedOrderTest(unittest.TestCase):
    def test_classic_orders(self):
        self.assertEqual(bracket.seed_order(2), [0, 1])
        self.assertEqual(bracket.seed_order(4), [0, 3, 1, 2])
        self.assertEqual(bracket.seed_order(8), [0, 7, 3, 4, 1, 6, 2, 5])

    def test_every_position_appears_exactly_once(self):
        for size in (2, 4, 8, 16):
            order = bracket.seed_order(size)
            self.assertEqual(sorted(order), list(range(size)))

    def test_top_seeds_meet_the_bottom_seeds_first(self):
        pairings = bracket.first_round_pairings(8)
        self.assertIn((0, 7), pairings)
        self.assertIn((1, 6), pairings)


class PairingTest(unittest.TestCase):
    def test_full_bracket_has_no_bye(self):
        for count in (2, 4, 8, 16):
            pairings = bracket.first_round_pairings(count)
            self.assertEqual(len(pairings), count // 2)
            self.assertTrue(all(None not in pair for pair in pairings))

    def test_every_player_plays_exactly_once_in_the_first_round(self):
        for count in range(2, bracket.MAX_PLAYERS + 1):
            seen = [value for pair in bracket.first_round_pairings(count)
                    for value in pair if value is not None]
            self.assertEqual(sorted(seen), list(range(count)),
                             f"placement incorrect pour {count} joueurs")

    def test_byes_go_to_the_best_seeds(self):
        exempted = {pair[0] if pair[1] is None else pair[1]
                    for pair in bracket.first_round_pairings(5)
                    if None in pair}
        self.assertEqual(exempted, {0, 1, 2})

    def test_bye_count_matches_the_gap_to_the_bracket_size(self):
        for count in range(2, bracket.MAX_PLAYERS + 1):
            description = bracket.describe(count)
            byes = sum(1 for pair in description["first_round"] if None in pair)
            self.assertEqual(byes, description["byes"])

    def test_a_three_player_tournament_gives_one_bye(self):
        pairings = bracket.first_round_pairings(3)
        self.assertEqual(len(pairings), 2)
        self.assertEqual(sum(1 for pair in pairings if None in pair), 1)


class ProgressionTest(unittest.TestCase):
    def test_winners_converge_towards_the_final(self):
        self.assertEqual(bracket.parent_slot(0, 0), (1, 0))
        self.assertEqual(bracket.parent_slot(0, 1), (1, 0))
        self.assertEqual(bracket.parent_side(0), 0)
        self.assertEqual(bracket.parent_side(1), 1)

    def test_the_whole_bracket_collapses_to_a_single_final_match(self):
        slots = list(range(8))
        round_index = 0
        while len(slots) > 1:
            slots = sorted({bracket.parent_slot(round_index, slot)[1] for slot in slots})
            round_index += 1
        self.assertEqual(slots, [0])
        self.assertEqual(round_index, bracket.rounds_count(16) - 1)


if __name__ == "__main__":
    unittest.main()
