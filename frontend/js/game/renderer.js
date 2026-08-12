/**
 * Rendu du terrain sur un canvas 2D.
 *
 * Le client ne simule rien : il recoit ~30 instantanes par seconde et les
 * affiche a 60 images par seconde. L'ecart est comble par **interpolation**
 * entre les deux instantanes qui encadrent l'instant affiche, avec un retard
 * volontaire de 100 ms (INTERP_DELAY). Sans ce retard, une trame reseau en
 * retard laisserait un trou et la balle sauterait ; avec lui, on interpole
 * toujours entre deux etats connus au lieu d'extrapoler dans le vide.
 *
 * Consequence assumee : on affiche le jeu tel qu'il etait il y a 100 ms. C'est
 * imperceptible a l'oeil et bien plus stable qu'une prediction qui se corrige.
 */

const INTERP_DELAY = 100;   // ms
const BUFFER_MAX = 40;      // ~1,3 s d'historique, largement suffisant

const COLORS = {
  court: '#05070b',
  line: '#1d2635',
  paddle: '#e8ecf3',
  ball: '#7bdcb5',
  score: '#39485e',
};

function lerp(from, to, ratio) {
  return from + (to - from) * ratio;
}

export class PongRenderer {
  /**
   * @param {HTMLCanvasElement} canvas
   * @param {object} geometry  constantes renvoyees par le serveur
   */
  constructor(canvas, geometry) {
    this.canvas = canvas;
    this.context = canvas.getContext('2d', { alpha: false });
    this.setGeometry(geometry);

    this.buffer = [];          // { at: ms local, state }
    this.latest = null;        // dernier instantane recu, brut
    this.frame = null;
    this.flash = 0;            // duree restante d'un eclat apres un point

    // Prediction locale de sa propre raquette (voir enablePrediction).
    this.predictSide = null;
    this.predictY = null;
    this.predictDir = 0;
    this.paddleSpeed = geometry.paddle_speed;
  }

  /**
   * Active la prediction locale d'une raquette.
   *
   * Sans elle, appuyer sur une touche ne se voit qu'apres un aller-retour
   * reseau plus les 100 ms d'interpolation : injouable des que la latence
   * depasse quelques dizaines de millisecondes. Avec elle, sa propre raquette
   * repond immediatement, tandis que la balle et la raquette adverse restent
   * affichees telles que le serveur les a annoncees — c'est-a-dire sans jamais
   * mentir sur ce qui fait autorite.
   *
   * L'ecart avec la position du serveur est resorbe progressivement, sauf s'il
   * devient trop grand (rebond sur un mur, correction) : dans ce cas on saute
   * directement a la position officielle.
   */
  enablePrediction(side) {
    this.predictSide = side;
    this.predictDir = 0;
    this.predictY = null;
  }

  setDirection(direction) {
    this.predictDir = direction;
  }

  setGeometry(geometry) {
    const [width, height] = geometry.field;
    this.width = width;
    this.height = height;
    this.paddleW = geometry.paddle[0];
    this.paddleH = geometry.paddle[1];
    this.margin = geometry.paddle_margin;
    this.ballRadius = geometry.ball_radius;

    // Resolution interne fixe : le CSS l'etire ensuite. Le rapport 4/3 du
    // terrain est celui du canvas, donc aucune deformation.
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    this.canvas.width = Math.round(width * ratio);
    this.canvas.height = Math.round(height * ratio);
    this.scale = ratio;
  }

  pushState(state) {
    this.latest = state;
    this.buffer.push({ at: performance.now(), state });
    if (this.buffer.length > BUFFER_MAX) this.buffer.shift();
  }

  /** Signale un point marque : un bref eclat rend le score plus lisible. */
  pulse() {
    this.flash = 220;
  }

  start() {
    if (this.frame !== null) return;
    let previous = performance.now();
    const loop = (now) => {
      const dt = Math.min((now - previous) / 1000, 0.1);   // borne les gros a-coups
      this.flash = Math.max(0, this.flash - (now - previous));
      previous = now;

      const state = this.sample(now - INTERP_DELAY);
      this.draw(this.applyPrediction(state, dt));
      this.frame = window.requestAnimationFrame(loop);
    };
    this.frame = window.requestAnimationFrame(loop);
  }

  /** Remplace la position de sa propre raquette par la position predite. */
  applyPrediction(state, dt) {
    if (state === null || this.predictSide === null) return state;

    const serverY = state.paddles[this.predictSide];
    if (this.predictY === null) {
      this.predictY = serverY;
      return state;
    }

    // Les raquettes ne bougent ni en pause, ni une fois la partie terminee :
    // predire un mouvement afficherait une raquette qui glisse toute seule.
    const running = state.status === 'playing' || state.status === 'countdown';
    if (running && this.predictDir !== 0) {
      const half = this.paddleH / 2;
      this.predictY = Math.min(Math.max(
        this.predictY + this.predictDir * this.paddleSpeed * dt, half), this.height - half);
    }

    const error = serverY - this.predictY;
    if (Math.abs(error) > 60) {
      this.predictY = serverY;             // trop loin : on se recale d'un coup
    } else {
      this.predictY += error * 0.12;       // sinon on rattrape en douceur
    }

    const paddles = state.paddles.slice();
    paddles[this.predictSide] = this.predictY;
    return { ...state, paddles };
  }

  stop() {
    if (this.frame !== null) {
      window.cancelAnimationFrame(this.frame);
      this.frame = null;
    }
  }

  /** Etat a afficher pour un instant donne, interpole entre deux instantanes. */
  sample(renderTime) {
    if (this.buffer.length === 0) return null;
    if (this.buffer.length === 1) return this.buffer[0].state;

    for (let index = this.buffer.length - 1; index > 0; index -= 1) {
      const after = this.buffer[index];
      const before = this.buffer[index - 1];
      if (before.at <= renderTime && renderTime <= after.at) {
        const span = after.at - before.at;
        const ratio = span > 0 ? (renderTime - before.at) / span : 1;
        return {
          ...after.state,
          ball: [
            lerp(before.state.ball[0], after.state.ball[0], ratio),
            lerp(before.state.ball[1], after.state.ball[1], ratio),
          ],
          paddles: [
            lerp(before.state.paddles[0], after.state.paddles[0], ratio),
            lerp(before.state.paddles[1], after.state.paddles[1], ratio),
          ],
        };
      }
    }

    // renderTime est hors de la fenetre bufferisee : soit la connexion a
    // hoquete, soit la partie vient de commencer. On affiche l'etat le plus
    // proche plutot que de figer un ecran vide.
    return renderTime < this.buffer[0].at
      ? this.buffer[0].state
      : this.buffer[this.buffer.length - 1].state;
  }

  draw(state) {
    const context = this.context;
    context.save();
    context.scale(this.scale, this.scale);

    context.fillStyle = COLORS.court;
    context.fillRect(0, 0, this.width, this.height);

    this.drawNet(context);

    if (state) {
      this.drawScores(context, state.scores);
      this.drawPaddles(context, state.paddles);
      // Pendant le decompte, la balle est au centre et immobile : on la
      // masque pour que le decompte affiche soit sans ambiguite.
      if (state.status !== 'countdown') this.drawBall(context, state.ball);
      if (state.status === 'countdown') this.drawCountdown(context, state.timer);
      if (state.status === 'paused') this.drawBanner(context, 'En pause');
    }

    context.restore();
  }

  drawNet(context) {
    // Filet en pointilles, comme sur la borne d'origine.
    context.fillStyle = COLORS.line;
    const dash = 14;
    const gap = 12;
    const x = this.width / 2 - 2;
    for (let y = gap; y < this.height - gap; y += dash + gap) {
      context.fillRect(x, y, 4, dash);
    }
  }

  drawScores(context, scores) {
    context.fillStyle = this.flash > 0 ? COLORS.ball : COLORS.score;
    context.font = 'bold 72px "Courier New", monospace';
    context.textBaseline = 'top';

    context.textAlign = 'right';
    context.fillText(String(scores[0]), this.width / 2 - 40, 28);
    context.textAlign = 'left';
    context.fillText(String(scores[1]), this.width / 2 + 40, 28);
  }

  drawPaddles(context, paddles) {
    context.fillStyle = COLORS.paddle;
    const top = (y) => y - this.paddleH / 2;
    context.fillRect(this.margin, top(paddles[0]), this.paddleW, this.paddleH);
    context.fillRect(this.width - this.margin - this.paddleW, top(paddles[1]),
      this.paddleW, this.paddleH);
  }

  drawBall(context, ball) {
    // Balle carree : c'est ainsi qu'elle apparaissait sur le Pong de 1972.
    const size = this.ballRadius * 2;
    context.fillStyle = COLORS.ball;
    context.fillRect(ball[0] - this.ballRadius, ball[1] - this.ballRadius, size, size);
  }

  drawCountdown(context, timer) {
    const seconds = Math.max(1, Math.ceil(timer));
    context.fillStyle = COLORS.paddle;
    context.font = 'bold 96px "Courier New", monospace';
    context.textAlign = 'center';
    context.textBaseline = 'middle';
    context.fillText(String(seconds), this.width / 2, this.height / 2);
  }

  drawBanner(context, message) {
    context.fillStyle = 'rgba(5, 7, 11, 0.72)';
    context.fillRect(0, this.height / 2 - 50, this.width, 100);
    context.fillStyle = COLORS.paddle;
    context.font = 'bold 40px "Courier New", monospace';
    context.textAlign = 'center';
    context.textBaseline = 'middle';
    context.fillText(message, this.width / 2, this.height / 2);
  }
}
