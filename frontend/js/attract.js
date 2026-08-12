/**
 * Ecran d'attente de la page d'accueil.
 *
 * Les bornes d'arcade jouaient toutes seules quand personne n'etait devant :
 * c'est l'« attract mode », destine a montrer le jeu aux passants. Cette
 * animation en reprend le principe.
 *
 * Elle est purement decorative et tourne dans le navigateur. Ce n'est PAS le
 * jeu : la vraie partie est simulee par le serveur (game/engine.py), le client
 * n'y calcule aucune physique. Les deux ne partagent aucun code, et ce qui est
 * dessine ici n'a aucune consequence.
 */

const W = 320;              // resolution interne, volontairement basse
const H = 160;
const PADDLE_W = 5;
const PADDLE_H = 34;
const MARGIN = 10;
const BALL = 5;

export function startAttract(canvas) {
  const context = canvas.getContext('2d', { alpha: false });
  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = W * ratio;
  canvas.height = H * ratio;

  const state = {
    ball: { x: W / 2, y: H / 2, vx: 92, vy: 54 },
    left: H / 2,
    right: H / 2,
    scores: [0, 0],
  };

  let frame = null;
  let previous = performance.now();

  // Chaque raquette suit la balle avec un retard et une vitesse plafonnee :
  // elles se manquent de temps en temps, ce qui fait vivre l'echange. Une
  // poursuite parfaite donnerait un match figé, sans aucun point marque.
  const track = (current, target, speed, dt) => {
    const delta = target - current;
    const step = Math.max(-speed * dt, Math.min(speed * dt, delta));
    return Math.min(Math.max(current + step, PADDLE_H / 2), H - PADDLE_H / 2);
  };

  const reset = (towards) => {
    state.ball.x = W / 2;
    state.ball.y = H / 2;
    state.ball.vx = towards * 92;
    state.ball.vy = (Math.random() * 2 - 1) * 55;
  };

  const step = (dt) => {
    const ball = state.ball;
    ball.x += ball.vx * dt;
    ball.y += ball.vy * dt;

    if (ball.y < BALL / 2) { ball.y = BALL / 2; ball.vy = -ball.vy; }
    if (ball.y > H - BALL / 2) { ball.y = H - BALL / 2; ball.vy = -ball.vy; }

    state.left = track(state.left, ball.y, 74, dt);
    state.right = track(state.right, ball.y, 68, dt);

    const leftEdge = MARGIN + PADDLE_W;
    if (ball.vx < 0 && ball.x - BALL / 2 <= leftEdge
        && Math.abs(ball.y - state.left) < PADDLE_H / 2 + BALL) {
      ball.x = leftEdge + BALL / 2;
      ball.vx = -ball.vx;
      ball.vy += (ball.y - state.left) * 0.9;
    }

    const rightEdge = W - MARGIN - PADDLE_W;
    if (ball.vx > 0 && ball.x + BALL / 2 >= rightEdge
        && Math.abs(ball.y - state.right) < PADDLE_H / 2 + BALL) {
      ball.x = rightEdge - BALL / 2;
      ball.vx = -ball.vx;
      ball.vy += (ball.y - state.right) * 0.9;
    }

    if (ball.x < -BALL) { state.scores[1] += 1; reset(1); }
    if (ball.x > W + BALL) { state.scores[0] += 1; reset(-1); }

    // Les scores restent a un chiffre : au-dela, l'affichage deborderait.
    if (state.scores[0] > 9 || state.scores[1] > 9) state.scores = [0, 0];
  };

  const draw = () => {
    context.save();
    context.scale(ratio, ratio);

    context.fillStyle = '#000000';
    context.fillRect(0, 0, W, H);

    context.fillStyle = '#1f2a33';
    for (let y = 6; y < H - 6; y += 12) context.fillRect(W / 2 - 1, y, 2, 7);

    context.fillStyle = '#2b3b45';
    context.font = '20px "Press Start 2P", monospace';
    context.textBaseline = 'top';
    context.textAlign = 'right';
    context.fillText(String(state.scores[0]), W / 2 - 18, 12);
    context.textAlign = 'left';
    context.fillText(String(state.scores[1]), W / 2 + 18, 12);

    context.fillStyle = '#e6f2ea';
    context.fillRect(MARGIN, state.left - PADDLE_H / 2, PADDLE_W, PADDLE_H);
    context.fillRect(W - MARGIN - PADDLE_W, state.right - PADDLE_H / 2, PADDLE_W, PADDLE_H);

    context.fillStyle = '#35f08a';
    context.fillRect(state.ball.x - BALL / 2, state.ball.y - BALL / 2, BALL, BALL);

    context.restore();
  };

  const loop = (now) => {
    const dt = Math.min((now - previous) / 1000, 0.05);
    previous = now;
    step(dt);
    draw();
    frame = window.requestAnimationFrame(loop);
  };

  // Reglage « reduire les animations » : on dessine une image fixe et on
  // s'arrete la.
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    draw();
    return () => {};
  }

  frame = window.requestAnimationFrame(loop);
  return () => {
    if (frame !== null) window.cancelAnimationFrame(frame);
    frame = null;
  };
}
