"""Tests du moteur physique."""

import math
import unittest

from game import engine
from game.engine import LEFT, RIGHT, PongEngine


def play(instance: PongEngine, seconds: float, inputs=None) -> list[dict]:
    """Fait tourner la simulation et retourne tous les evenements produits."""
    events = []
    for step in range(int(seconds * engine.TICK_RATE)):
        if inputs:
            inputs(instance, step)
        events.extend(instance.tick())
    return events


class PaddleRulesTest(unittest.TestCase):
    """« All players must adhere to the same rules, including paddle speed. »"""

    def test_both_paddles_move_at_the_same_speed(self):
        game = PongEngine(seed=1)
        game.set_input(LEFT, -1)
        game.set_input(RIGHT, 1)

        start_left = game.paddles[LEFT].y
        start_right = game.paddles[RIGHT].y
        for _ in range(30):
            game.tick()

        moved_left = abs(game.paddles[LEFT].y - start_left)
        moved_right = abs(game.paddles[RIGHT].y - start_right)
        self.assertAlmostEqual(moved_left, moved_right, places=9)
        self.assertAlmostEqual(moved_left, engine.PADDLE_SPEED * 30 * engine.DT, places=6)

    def test_paddles_stay_inside_the_field(self):
        game = PongEngine(seed=2)
        game.set_input(LEFT, -1)
        game.set_input(RIGHT, 1)
        play(game, 5.0)

        half = engine.PADDLE_H / 2
        for paddle in game.paddles:
            self.assertGreaterEqual(paddle.y, half - 1e-9)
            self.assertLessEqual(paddle.y, engine.FIELD_H - half + 1e-9)

    def test_input_is_normalised_to_three_values(self):
        game = PongEngine(seed=3)
        game.set_input(LEFT, 999)
        self.assertEqual(game.paddles[LEFT].direction, 1)
        game.set_input(LEFT, -999)
        self.assertEqual(game.paddles[LEFT].direction, -1)
        game.set_input(LEFT, 0)
        self.assertEqual(game.paddles[LEFT].direction, 0)

    def test_unknown_player_index_is_ignored(self):
        game = PongEngine(seed=4)
        game.set_input(7, 1)
        self.assertEqual(len(game.paddles), 2)


class DeterminismTest(unittest.TestCase):
    def test_same_seed_and_inputs_produce_the_same_game(self):
        def scripted(game, step):
            game.set_input(LEFT, 1 if (step // 20) % 2 == 0 else -1)
            game.set_input(RIGHT, -1 if (step // 17) % 2 == 0 else 1)

        first = PongEngine(seed=1234)
        second = PongEngine(seed=1234)
        play(first, 12.0, scripted)
        play(second, 12.0, scripted)

        self.assertEqual(first.snapshot(), second.snapshot())
        self.assertEqual(first.stats(), second.stats())

    def test_different_seeds_diverge(self):
        first = PongEngine(seed=1)
        second = PongEngine(seed=2)
        play(first, 10.0)
        play(second, 10.0)
        self.assertNotEqual(first.snapshot(), second.snapshot())


class BallPhysicsTest(unittest.TestCase):
    def test_ball_never_leaves_the_field_sideways_without_scoring(self):
        """La balle ne doit jamais traverser une raquette (effet tunnel)."""
        game = PongEngine(seed=7, points_to_win=engine.MAX_POINTS_TO_WIN)

        def follow(instance, _step):
            for index, paddle in enumerate(instance.paddles):
                delta = instance.ball.y - paddle.y
                instance.set_input(index, 1 if delta > 2 else -1 if delta < -2 else 0)

        events = play(game, 60.0, follow)

        goals = [event for event in events if event["type"] == "score"]
        self.assertEqual(goals, [], "une balle a traverse une raquette qui la suivait")
        self.assertGreater(game.total_hits, 20, "la balle n'a quasiment pas ete jouee")

    def test_ball_speed_is_capped(self):
        game = PongEngine(seed=11, points_to_win=engine.MAX_POINTS_TO_WIN)

        def follow(instance, _step):
            for index, paddle in enumerate(instance.paddles):
                delta = instance.ball.y - paddle.y
                instance.set_input(index, 1 if delta > 2 else -1 if delta < -2 else 0)

        play(game, 60.0, follow)
        self.assertLessEqual(game.ball.speed, engine.BALL_SPEED_MAX + 1e-6)

    def test_ball_stays_between_the_horizontal_walls(self):
        game = PongEngine(seed=13, points_to_win=engine.MAX_POINTS_TO_WIN)
        for _ in range(60 * 30):
            game.tick()
            self.assertGreaterEqual(game.ball.y, -1e-6)
            self.assertLessEqual(game.ball.y, engine.FIELD_H + 1e-6)

    def test_bounce_angle_never_exceeds_the_maximum(self):
        game = PongEngine(seed=17)
        game.status = engine.STATUS_PLAYING
        game.ball.x = engine.PADDLE_MARGIN + engine.PADDLE_W + engine.BALL_RADIUS - 0.5
        game.ball.y = game.paddles[LEFT].y + engine.PADDLE_H / 2
        game.ball.vx = -engine.BALL_SPEED_START
        game.ball.vy = 0.0

        game.tick()

        angle = abs(math.atan2(game.ball.vy, game.ball.vx))
        self.assertLessEqual(angle, engine.MAX_BOUNCE_ANGLE + 1e-6)
        self.assertGreater(game.ball.vx, 0, "la balle doit repartir vers la droite")


class ScoringTest(unittest.TestCase):
    def test_a_missed_ball_scores_for_the_opponent(self):
        game = PongEngine(seed=21)
        game.status = engine.STATUS_PLAYING
        game.ball.x = engine.BALL_RADIUS
        game.ball.y = 30.0
        game.paddles[LEFT].y = engine.FIELD_H - 60
        game.ball.vx = -engine.BALL_SPEED_START
        game.ball.vy = 0.0

        events = play(game, 1.0)

        scored = [event for event in events if event["type"] == "score"]
        self.assertEqual(len(scored), 1)
        self.assertEqual(scored[0]["player"], RIGHT)
        self.assertEqual(game.scores, [0, 1])

    def test_the_ball_is_served_towards_the_player_who_conceded(self):
        game = PongEngine(seed=23)
        game.status = engine.STATUS_PLAYING
        game.ball.x = engine.BALL_RADIUS
        game.ball.y = 30.0
        game.paddles[LEFT].y = engine.FIELD_H - 60
        game.ball.vx = -engine.BALL_SPEED_START
        game.ball.vy = 0.0

        play(game, 1.0)

        self.assertLess(game.ball.vx, 0)

    def test_match_ends_at_the_target_score(self):
        game = PongEngine(seed=29, points_to_win=3)
        game.scores = [2, 0]
        game.status = engine.STATUS_PLAYING
        game.ball.x = engine.FIELD_W - engine.BALL_RADIUS
        game.ball.y = 30.0
        game.paddles[RIGHT].y = engine.FIELD_H - 60
        game.ball.vx = engine.BALL_SPEED_START
        game.ball.vy = 0.0

        events = play(game, 1.0)

        self.assertEqual(game.status, engine.STATUS_FINISHED)
        self.assertEqual(game.winner, LEFT)
        self.assertTrue(any(event["type"] == "end" for event in events))

    def test_finished_game_ignores_further_ticks(self):
        game = PongEngine(seed=31, points_to_win=1)
        game.scores = [1, 0]
        game.status = engine.STATUS_FINISHED
        before = game.snapshot()
        play(game, 2.0)
        self.assertEqual(game.snapshot(), before)

    def test_points_to_win_is_clamped(self):
        self.assertEqual(PongEngine(points_to_win=0).points_to_win, engine.MIN_POINTS_TO_WIN)
        self.assertEqual(PongEngine(points_to_win=999).points_to_win, engine.MAX_POINTS_TO_WIN)


class InterruptionTest(unittest.TestCase):
    def test_pause_freezes_everything_and_resume_restarts_with_a_countdown(self):
        game = PongEngine(seed=37)
        play(game, engine.COUNTDOWN + 0.3)
        self.assertEqual(game.status, engine.STATUS_PLAYING)

        position = (game.ball.x, game.ball.y)
        game.set_input(LEFT, 1)
        paddle_y = game.paddles[LEFT].y

        game.pause()
        play(game, 1.0)
        self.assertEqual((game.ball.x, game.ball.y), position, "la balle a bouge en pause")
        self.assertEqual(game.paddles[LEFT].y, paddle_y, "une raquette a bouge en pause")

        game.resume()
        self.assertEqual(game.status, engine.STATUS_COUNTDOWN)

        play(game, engine.SERVE_DELAY + 0.3)
        self.assertEqual(game.status, engine.STATUS_PLAYING)
        self.assertNotEqual((game.ball.x, game.ball.y), position)

    def test_forfeit_awards_the_match_to_the_opponent(self):
        game = PongEngine(seed=41, points_to_win=5)
        game.scores = [1, 3]
        game.forfeit(loser=RIGHT)

        self.assertEqual(game.status, engine.STATUS_FINISHED)
        self.assertEqual(game.winner, LEFT)
        self.assertGreaterEqual(game.scores[LEFT], 5)

    def test_forfeit_after_the_end_changes_nothing(self):
        game = PongEngine(seed=43, points_to_win=1)
        game.status = engine.STATUS_FINISHED
        game.winner = LEFT
        game.forfeit(loser=LEFT)
        self.assertEqual(game.winner, LEFT)


class SnapshotTest(unittest.TestCase):
    def test_snapshot_is_json_friendly_and_complete(self):
        game = PongEngine(seed=47)
        play(game, 3.0)
        snapshot = game.snapshot()

        self.assertEqual(
            set(snapshot),
            {"t", "status", "timer", "ball", "paddles", "scores", "winner"},
        )
        self.assertEqual(len(snapshot["ball"]), 2)
        self.assertEqual(len(snapshot["paddles"]), 2)

    def test_geometry_exposes_the_shared_paddle_speed(self):
        self.assertEqual(engine.geometry()["paddle_speed"], engine.PADDLE_SPEED)
        self.assertEqual(engine.geometry()["field"], [engine.FIELD_W, engine.FIELD_H])


if __name__ == "__main__":
    unittest.main()
