"""Moteur physique du Pong — autoritatif et sans dependance a Django."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

FIELD_W = 800.0
FIELD_H = 600.0

PADDLE_W = 12.0
PADDLE_H = 96.0
PADDLE_MARGIN = 24.0

BALL_RADIUS = 8.0

PADDLE_SPEED = 420.0

BALL_SPEED_START = 340.0
BALL_SPEED_MAX = 820.0
BALL_SPEED_GAIN = 1.045

MAX_BOUNCE_ANGLE = math.radians(58.0)

TICK_RATE = 60
DT = 1.0 / TICK_RATE
SERVE_DELAY = 1.2
COUNTDOWN = 3.0

DEFAULT_POINTS_TO_WIN = 5
MIN_POINTS_TO_WIN = 1
MAX_POINTS_TO_WIN = 21

STATUS_COUNTDOWN = "countdown"
STATUS_PLAYING = "playing"
STATUS_PAUSED = "paused"
STATUS_FINISHED = "finished"

LEFT = 0
RIGHT = 1


def clamp(value: float, low: float, high: float) -> float:
    return low if value < low else high if value > high else value


@dataclass
class Paddle:
    """Raquette : `y` est le centre, `direction` vaut -1, 0 ou +1."""

    y: float = FIELD_H / 2
    direction: int = 0

    @property
    def top(self) -> float:
        return self.y - PADDLE_H / 2

    @property
    def bottom(self) -> float:
        return self.y + PADDLE_H / 2


@dataclass
class Ball:
    x: float = FIELD_W / 2
    y: float = FIELD_H / 2
    vx: float = 0.0
    vy: float = 0.0

    @property
    def speed(self) -> float:
        return math.hypot(self.vx, self.vy)


@dataclass
class PongEngine:
    """Une partie. `tick()` avance l'etat d'exactement un pas de temps."""

    points_to_win: int = DEFAULT_POINTS_TO_WIN
    seed: int = 0

    paddles: list[Paddle] = field(default_factory=lambda: [Paddle(), Paddle()])
    ball: Ball = field(default_factory=Ball)
    scores: list[int] = field(default_factory=lambda: [0, 0])

    status: str = STATUS_COUNTDOWN
    tick_count: int = 0
    timer: float = COUNTDOWN
    winner: int | None = None
    rally_length: int = 0
    longest_rally: int = 0
    total_hits: int = 0

    def __post_init__(self) -> None:
        self.points_to_win = int(clamp(self.points_to_win, MIN_POINTS_TO_WIN, MAX_POINTS_TO_WIN))
        self._random = random.Random(self.seed)
        self._prepare_serve(toward=self._random.choice([LEFT, RIGHT]), delay=COUNTDOWN)


    def set_input(self, player: int, direction: int) -> None:
        """Enregistre l'intention d'un joueur : -1 (haut), 0 (immobile), +1 (bas)."""
        if player not in (LEFT, RIGHT):
            return
        self.paddles[player].direction = -1 if direction < 0 else 1 if direction > 0 else 0


    def tick(self, dt: float = DT) -> list[dict]:
        """Avance la simulation. Retourne les evenements survenus pendant le pas."""
        if self.status == STATUS_FINISHED:
            return []

        self.tick_count += 1
        events: list[dict] = []

        if self.status == STATUS_PAUSED:
            return events

        self._move_paddles(dt)

        if self.status == STATUS_COUNTDOWN:
            self.timer -= dt
            if self.timer <= 0:
                self.status = STATUS_PLAYING
                self.timer = 0.0
                events.append({"type": "serve"})
            return events

        self._move_ball(dt, events)
        return events

    def _move_paddles(self, dt: float) -> None:
        half = PADDLE_H / 2
        for paddle in self.paddles:
            if paddle.direction:
                paddle.y = clamp(paddle.y + paddle.direction * PADDLE_SPEED * dt,
                                 half, FIELD_H - half)

    def _move_ball(self, dt: float, events: list[dict]) -> None:
        distance = self.ball.speed * dt
        steps = max(1, math.ceil(distance / (BALL_RADIUS * 0.75)))
        sub_dt = dt / steps

        for _ in range(steps):
            self.ball.x += self.ball.vx * sub_dt
            self.ball.y += self.ball.vy * sub_dt

            self._bounce_walls(events)
            self._bounce_paddles(events)

            scorer = self._check_goal()
            if scorer is not None:
                self._register_point(scorer, events)
                return

    def _bounce_walls(self, events: list[dict]) -> None:
        if self.ball.y - BALL_RADIUS <= 0 and self.ball.vy < 0:
            self.ball.y = BALL_RADIUS
            self.ball.vy = -self.ball.vy
            events.append({"type": "wall"})
        elif self.ball.y + BALL_RADIUS >= FIELD_H and self.ball.vy > 0:
            self.ball.y = FIELD_H - BALL_RADIUS
            self.ball.vy = -self.ball.vy
            events.append({"type": "wall"})

    def _bounce_paddles(self, events: list[dict]) -> None:
        for index, paddle in enumerate(self.paddles):
            left_x, right_x = paddle_bounds(index)

            if self.ball.x + BALL_RADIUS < left_x or self.ball.x - BALL_RADIUS > right_x:
                continue
            if abs(self.ball.y - paddle.y) > PADDLE_H / 2 + BALL_RADIUS:
                continue
            if index == LEFT and self.ball.vx >= 0:
                continue
            if index == RIGHT and self.ball.vx <= 0:
                continue

            offset = clamp((self.ball.y - paddle.y) / (PADDLE_H / 2), -1.0, 1.0)
            angle = offset * MAX_BOUNCE_ANGLE
            speed = min(self.ball.speed * BALL_SPEED_GAIN, BALL_SPEED_MAX)

            direction = 1.0 if index == LEFT else -1.0
            self.ball.vx = direction * speed * math.cos(angle)
            self.ball.vy = speed * math.sin(angle)

            self.ball.x = (right_x + BALL_RADIUS) if index == LEFT else (left_x - BALL_RADIUS)

            self.rally_length += 1
            self.total_hits += 1
            self.longest_rally = max(self.longest_rally, self.rally_length)
            events.append({"type": "hit", "player": index, "offset": round(offset, 3)})
            return

    def _check_goal(self) -> int | None:
        if self.ball.x + BALL_RADIUS < 0:
            return RIGHT
        if self.ball.x - BALL_RADIUS > FIELD_W:
            return LEFT
        return None

    def _register_point(self, scorer: int, events: list[dict]) -> None:
        self.scores[scorer] += 1
        events.append({
            "type": "score",
            "player": scorer,
            "scores": list(self.scores),
            "rally": self.rally_length,
        })
        self.rally_length = 0

        if self.scores[scorer] >= self.points_to_win:
            self.status = STATUS_FINISHED
            self.winner = scorer
            events.append({"type": "end", "winner": scorer, "scores": list(self.scores)})
            return

        self._prepare_serve(toward=1 - scorer, delay=SERVE_DELAY)

    def _prepare_serve(self, *, toward: int, delay: float) -> None:
        """Replace la balle au centre et l'oriente vers le cote `toward`."""
        self.ball.x = FIELD_W / 2
        self.ball.y = FIELD_H / 2

        angle = self._random.uniform(-math.radians(30), math.radians(30))
        direction = -1.0 if toward == LEFT else 1.0
        self.ball.vx = direction * BALL_SPEED_START * math.cos(angle)
        self.ball.vy = BALL_SPEED_START * math.sin(angle)

        self.status = STATUS_COUNTDOWN
        self.timer = delay


    def snapshot(self) -> dict:
        """Instantane compact envoye aux clients (30 fois par seconde)."""
        return {
            "t": self.tick_count,
            "status": self.status,
            "timer": round(self.timer, 2),
            "ball": [round(self.ball.x, 1), round(self.ball.y, 1)],
            "paddles": [round(self.paddles[LEFT].y, 1), round(self.paddles[RIGHT].y, 1)],
            "scores": list(self.scores),
            "winner": self.winner,
        }

    def stats(self) -> dict:
        """Agregats de fin de partie, repris par les tableaux de bord."""
        return {
            "ticks": self.tick_count,
            "duration_seconds": round(self.tick_count * DT, 1),
            "total_hits": self.total_hits,
            "longest_rally": self.longest_rally,
        }

    def pause(self) -> None:
        if self.status in (STATUS_PLAYING, STATUS_COUNTDOWN):
            self.status = STATUS_PAUSED

    def resume(self) -> None:
        if self.status == STATUS_PAUSED:
            self.status = STATUS_COUNTDOWN
            self.timer = max(self.timer, SERVE_DELAY)

    def forfeit(self, loser: int) -> None:
        """Termine la partie sur abandon (deconnexion trop longue)."""
        if self.status == STATUS_FINISHED:
            return
        self.winner = 1 - loser
        self.scores[self.winner] = max(self.scores[self.winner], self.points_to_win)
        self.status = STATUS_FINISHED


def paddle_bounds(index: int) -> tuple[float, float]:
    """Abscisses des bords gauche et droit d'une raquette."""
    if index == LEFT:
        return PADDLE_MARGIN, PADDLE_MARGIN + PADDLE_W
    return FIELD_W - PADDLE_MARGIN - PADDLE_W, FIELD_W - PADDLE_MARGIN


def geometry() -> dict:
    """Constantes du terrain, envoyees au client pour qu'il dessine a l'echelle."""
    return {
        "field": [FIELD_W, FIELD_H],
        "paddle": [PADDLE_W, PADDLE_H],
        "paddle_margin": PADDLE_MARGIN,
        "ball_radius": BALL_RADIUS,
        "paddle_speed": PADDLE_SPEED,
        "tick_rate": TICK_RATE,
    }
