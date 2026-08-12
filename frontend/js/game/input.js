

const LEFT_KEYS = {
  KeyW: -1, KeyZ: -1,
  KeyS: 1,
};

const RIGHT_KEYS = {
  ArrowUp: -1,
  ArrowDown: 1,
};

export class KeyboardControls {

  constructor(sides, onChange) {
    this.sides = new Set(sides);
    this.onChange = onChange;
    this.pressed = new Map();
    this.current = new Map();

    this.handleKeyDown = this.handleKeyDown.bind(this);
    this.handleKeyUp = this.handleKeyUp.bind(this);
    this.handleBlur = this.handleBlur.bind(this);
  }


  resolve(code) {


    if (this.sides.size === 1) {
      const side = [...this.sides][0];
      const direction = LEFT_KEYS[code] ?? RIGHT_KEYS[code];
      return direction === undefined ? null : { side, direction };
    }
    if (code in LEFT_KEYS && this.sides.has(0)) return { side: 0, direction: LEFT_KEYS[code] };
    if (code in RIGHT_KEYS && this.sides.has(1)) return { side: 1, direction: RIGHT_KEYS[code] };
    return null;
  }

  handleKeyDown(event) {
    if (event.repeat) return;
    const resolved = this.resolve(event.code);
    if (!resolved) return;


    event.preventDefault();
    this.pressed.set(event.code, resolved);
    this.apply(resolved.side);
  }

  handleKeyUp(event) {
    if (!this.pressed.has(event.code)) return;
    const { side } = this.pressed.get(event.code);
    this.pressed.delete(event.code);
    this.apply(side);
  }


  handleBlur() {
    const sides = new Set([...this.pressed.values()].map((entry) => entry.side));
    this.pressed.clear();
    for (const side of sides) this.apply(side);
  }


  apply(side) {
    let direction = 0;
    for (const entry of this.pressed.values()) {
      if (entry.side === side) direction += entry.direction;
    }
    direction = Math.sign(direction);

    if (this.current.get(side) === direction) return;
    this.current.set(side, direction);
    this.onChange(side, direction);
  }

  attach() {
    window.addEventListener('keydown', this.handleKeyDown);
    window.addEventListener('keyup', this.handleKeyUp);
    window.addEventListener('blur', this.handleBlur);
  }

  detach() {
    window.removeEventListener('keydown', this.handleKeyDown);
    window.removeEventListener('keyup', this.handleKeyUp);
    window.removeEventListener('blur', this.handleBlur);


    for (const side of this.sides) {
      if (this.current.get(side)) this.onChange(side, 0);
    }
    this.pressed.clear();
    this.current.clear();
  }


  static hint(sides) {
    if (sides.length === 2) return 'Gauche : W / S  —  Droite : ↑ / ↓';
    return 'Deplacement : W / S ou ↑ / ↓';
  }
}
