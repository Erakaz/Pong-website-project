/**
 * Clavier.
 *
 * Deux joueurs sur le meme clavier, comme l'exige la partie obligatoire :
 * W/S (et Z/S en AZERTY) pour la raquette de gauche, les fleches Haut/Bas pour
 * celle de droite.
 *
 * Seuls les CHANGEMENTS de direction sont envoyes, jamais un message par
 * image : une touche maintenue produit un seul message, et le serveur continue
 * d'appliquer la direction jusqu'au relachement. Cela divise le trafic par
 * plusieurs dizaines et rend le jeu insensible a la frequence de repetition du
 * clavier.
 */

const LEFT_KEYS = {
  KeyW: -1, KeyZ: -1,      // W en QWERTY, Z en AZERTY
  KeyS: 1,
};

const RIGHT_KEYS = {
  ArrowUp: -1,
  ArrowDown: 1,
};

export class KeyboardControls {
  /**
   * @param {number[]} sides      cotes pilotes par ce client ([0,1] en local)
   * @param {(side:number, dir:number) => void} onChange
   */
  constructor(sides, onChange) {
    this.sides = new Set(sides);
    this.onChange = onChange;
    this.pressed = new Map();     // code touche -> { side, dir }
    this.current = new Map();     // side -> derniere direction envoyee

    this.handleKeyDown = this.handleKeyDown.bind(this);
    this.handleKeyUp = this.handleKeyUp.bind(this);
    this.handleBlur = this.handleBlur.bind(this);
  }

  /** Quelle raquette et quel sens pour une touche, ou null si non geree. */
  resolve(code) {
    // En partie a distance, le joueur ne pilote qu'une raquette : les deux
    // jeux de touches la commandent, pour ne pas avoir a se souvenir de quel
    // cote on joue.
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
    if (event.repeat) return;                       // deja pris en compte
    const resolved = this.resolve(event.code);
    if (!resolved) return;

    // Les fleches font defiler la page : c'est injouable si on ne l'empeche pas.
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

  /** Fenetre qui perd le focus : sinon la raquette resterait bloquee en haut. */
  handleBlur() {
    const sides = new Set([...this.pressed.values()].map((entry) => entry.side));
    this.pressed.clear();
    for (const side of sides) this.apply(side);
  }

  /**
   * Recalcule la direction d'une raquette a partir des touches enfoncees.
   * Haut et Bas simultanes s'annulent — plus previsible que « la derniere
   * touche gagne ».
   */
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
    // Relacher les raquettes en quittant : sans cela, revenir sur la page
    // retrouverait une raquette qui monte toute seule.
    for (const side of this.sides) {
      if (this.current.get(side)) this.onChange(side, 0);
    }
    this.pressed.clear();
    this.current.clear();
  }

  /** Libelle des touches, affiche sous le terrain. */
  static hint(sides) {
    if (sides.length === 2) return 'Gauche : W / S  —  Droite : ↑ / ↓';
    return 'Deplacement : W / S ou ↑ / ↓';
  }
}
