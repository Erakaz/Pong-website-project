

const INTERP_DELAY = 100;
const BUFFER_MAX = 40;


const COLORS = {
  court: '#000000',
  line: '#1f2a33',
  paddle: '#e6f2ea',
  ball: '#35f08a',
  score: '#2b3b45',
  scoreFlash: '#35f08a',
};

const FONT = '"Press Start 2P", "Courier New", monospace';

function lerp(from, to, ratio) {
  return from + (to - from) * ratio;
}

export class PongRenderer {

  constructor(canvas, geometry) {
    this.canvas = canvas;
    this.context = canvas.getContext('2d', { alpha: false });
    this.setGeometry(geometry);

    this.buffer = [];
    this.latest = null;
    this.frame = null;
    this.flash = 0;


    this.predictSide = null;
    this.predictY = null;
    this.predictDir = 0;
    this.paddleSpeed = geometry.paddle_speed;
  }


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


  pulse() {
    this.flash = 220;
  }

  start() {
    if (this.frame !== null) return;
    let previous = performance.now();
    const loop = (now) => {
      const dt = Math.min((now - previous) / 1000, 0.1);
      this.flash = Math.max(0, this.flash - (now - previous));
      previous = now;

      const state = this.sample(now - INTERP_DELAY);
      this.draw(this.applyPrediction(state, dt));
      this.frame = window.requestAnimationFrame(loop);
    };
    this.frame = window.requestAnimationFrame(loop);
  }


  applyPrediction(state, dt) {
    if (state === null || this.predictSide === null) return state;

    const serverY = state.paddles[this.predictSide];
    if (this.predictY === null) {
      this.predictY = serverY;
      return state;
    }


    const running = state.status === 'playing' || state.status === 'countdown';
    if (running && this.predictDir !== 0) {
      const half = this.paddleH / 2;
      this.predictY = Math.min(Math.max(
        this.predictY + this.predictDir * this.paddleSpeed * dt, half), this.height - half);
    }

    const error = serverY - this.predictY;
    if (Math.abs(error) > 60) {
      this.predictY = serverY;
    } else {
      this.predictY += error * 0.12;
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


      if (state.status !== 'countdown') this.drawBall(context, state.ball);
      if (state.status === 'countdown') this.drawCountdown(context, state.timer);
      if (state.status === 'paused') this.drawBanner(context, 'En pause');
    }

    context.restore();
  }

  drawNet(context) {

    context.fillStyle = COLORS.line;
    const dash = 14;
    const gap = 12;
    const x = this.width / 2 - 2;
    for (let y = gap; y < this.height - gap; y += dash + gap) {
      context.fillRect(x, y, 4, dash);
    }
  }

  drawScores(context, scores) {
    const flashing = this.flash > 0;
    context.fillStyle = flashing ? COLORS.scoreFlash : COLORS.score;
    context.font = `56px ${FONT}`;
    context.textBaseline = 'top';


    context.shadowColor = COLORS.ball;
    context.shadowBlur = flashing ? 22 : 0;

    context.textAlign = 'right';
    context.fillText(String(scores[0]), this.width / 2 - 44, 30);
    context.textAlign = 'left';
    context.fillText(String(scores[1]), this.width / 2 + 44, 30);

    context.shadowBlur = 0;
  }

  drawPaddles(context, paddles) {
    const top = (y) => y - this.paddleH / 2;
    context.fillStyle = COLORS.paddle;
    context.shadowColor = COLORS.paddle;
    context.shadowBlur = 12;
    context.fillRect(this.margin, top(paddles[0]), this.paddleW, this.paddleH);
    context.fillRect(this.width - this.margin - this.paddleW, top(paddles[1]),
      this.paddleW, this.paddleH);
    context.shadowBlur = 0;
  }

  drawBall(context, ball) {

    const size = this.ballRadius * 2;
    context.fillStyle = COLORS.ball;
    context.shadowColor = COLORS.ball;
    context.shadowBlur = 16;
    context.fillRect(ball[0] - this.ballRadius, ball[1] - this.ballRadius, size, size);
    context.shadowBlur = 0;
  }

  drawCountdown(context, timer) {
    const seconds = Math.max(1, Math.ceil(timer));
    context.fillStyle = COLORS.paddle;
    context.font = `72px ${FONT}`;
    context.textAlign = 'center';
    context.textBaseline = 'middle';
    context.shadowColor = COLORS.ball;
    context.shadowBlur = 24;
    context.fillText(String(seconds), this.width / 2, this.height / 2);
    context.shadowBlur = 0;
  }

  drawBanner(context, message) {
    context.fillStyle = 'rgba(0, 0, 0, 0.78)';
    context.fillRect(0, this.height / 2 - 46, this.width, 92);
    context.fillStyle = COLORS.line;
    context.fillRect(0, this.height / 2 - 46, this.width, 3);
    context.fillRect(0, this.height / 2 + 43, this.width, 3);

    context.fillStyle = COLORS.paddle;
    context.font = `22px ${FONT}`;
    context.textAlign = 'center';
    context.textBaseline = 'middle';
    context.fillText(message.toUpperCase(), this.width / 2, this.height / 2);
  }
}
