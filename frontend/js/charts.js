/**
 * Graphiques SVG minimalistes, ecrits a la main.
 *
 * Aucune bibliotheque de visualisation : trois formes suffisent aux tableaux
 * de bord demandes, et les dessiner soi-meme evite d'embarquer 200 Ko de
 * dependance pour tracer quelques rectangles. Le SVG s'adapte tout seul a la
 * largeur disponible grace au `viewBox`.
 *
 * Accessibilite : chaque graphique porte `role="img"` et une description
 * textuelle, et les memes chiffres sont toujours disponibles en toutes lettres
 * a cote — un graphique ne doit jamais etre le seul moyen d'acceder a une
 * information.
 */

const NS = 'http://www.w3.org/2000/svg';

const COLORS = {
  win: '#7bdcb5',
  loss: '#e06c75',
  neutral: '#4b5768',
  grid: '#29313f',
  text: '#8a95a5',
};

function svg(width, height, label) {
  const node = document.createElementNS(NS, 'svg');
  node.setAttribute('viewBox', `0 0 ${width} ${height}`);
  node.setAttribute('width', '100%');
  node.setAttribute('preserveAspectRatio', 'xMidYMid meet');
  node.setAttribute('role', 'img');
  node.setAttribute('aria-label', label);
  node.style.display = 'block';
  return node;
}

function shape(name, attributes) {
  const node = document.createElementNS(NS, name);
  for (const [key, value] of Object.entries(attributes)) {
    node.setAttribute(key, String(value));
  }
  return node;
}

function label(x, y, text, { anchor = 'middle', size = 11, fill = COLORS.text } = {}) {
  const node = shape('text', { x, y, 'text-anchor': anchor, 'font-size': size, fill });
  node.textContent = text;
  return node;
}

/**
 * Anneau victoires / defaites.
 * @param {number} wins
 * @param {number} losses
 */
export function donut(wins, losses) {
  const total = wins + losses;
  const size = 160;
  const radius = 60;
  const thickness = 18;
  const centre = size / 2;

  const node = svg(size, size,
    `Repartition : ${wins} victoire(s) et ${losses} defaite(s).`);

  node.appendChild(shape('circle', {
    cx: centre, cy: centre, r: radius, fill: 'none',
    stroke: total ? COLORS.loss : COLORS.grid, 'stroke-width': thickness,
  }));

  if (total > 0 && wins > 0) {
    const circumference = 2 * Math.PI * radius;
    const filled = (wins / total) * circumference;
    // Un arc dessine avec `stroke-dasharray` : un seul cercle suffit, pas
    // besoin de calculer un chemin.
    const arc = shape('circle', {
      cx: centre, cy: centre, r: radius, fill: 'none',
      stroke: COLORS.win, 'stroke-width': thickness,
      'stroke-dasharray': `${filled} ${circumference - filled}`,
      'stroke-dashoffset': circumference / 4,     // demarre en haut
      transform: `rotate(-90 ${centre} ${centre})`,
    });
    node.appendChild(arc);
  }

  const rate = total ? Math.round((wins / total) * 100) : 0;
  node.appendChild(label(centre, centre + 2, `${rate} %`,
    { size: 26, fill: '#e8ecf3' }));
  node.appendChild(label(centre, centre + 22, 'de victoires'));
  return node;
}

/**
 * Barres horizontales : bilan par adversaire.
 * @param {{opponent: string, wins: number, losses: number}[]} rows
 */
export function opponentBars(rows) {
  if (rows.length === 0) return null;

  const rowHeight = 30;
  const width = 420;
  const labelWidth = 120;
  const height = rows.length * rowHeight + 10;
  const maxPlayed = Math.max(...rows.map((row) => row.wins + row.losses));

  const node = svg(width, height, `Bilan contre ${rows.length} adversaire(s).`);

  rows.forEach((row, index) => {
    const y = index * rowHeight + 6;
    const usable = width - labelWidth - 40;
    const winWidth = (row.wins / maxPlayed) * usable;
    const lossWidth = (row.losses / maxPlayed) * usable;

    node.appendChild(label(labelWidth - 8, y + 14, row.opponent, { anchor: 'end' }));
    if (winWidth > 0) {
      node.appendChild(shape('rect', {
        x: labelWidth, y: y + 3, width: winWidth, height: 16, rx: 3, fill: COLORS.win,
      }));
    }
    if (lossWidth > 0) {
      node.appendChild(shape('rect', {
        x: labelWidth + winWidth, y: y + 3, width: lossWidth, height: 16, rx: 3,
        fill: COLORS.loss,
      }));
    }
    node.appendChild(label(labelWidth + winWidth + lossWidth + 6, y + 15,
      `${row.wins}V ${row.losses}D`, { anchor: 'start' }));
  });

  return node;
}

/**
 * Courbe des points marques et encaisses sur les derniers matchs.
 * @param {{for: number, against: number, opponent: string}[]} entries
 */
export function formLines(entries) {
  if (entries.length < 2) return null;

  const width = 460;
  const height = 180;
  const padding = { top: 12, right: 12, bottom: 26, left: 28 };
  const maximum = Math.max(2, ...entries.flatMap((entry) => [entry.for, entry.against]));

  const node = svg(width, height,
    `Points marques et encaisses sur les ${entries.length} derniers matchs.`);

  const x = (index) => padding.left
    + (index / (entries.length - 1)) * (width - padding.left - padding.right);
  const y = (value) => height - padding.bottom
    - (value / maximum) * (height - padding.top - padding.bottom);

  // Lignes de reperage horizontales.
  for (let step = 0; step <= maximum; step += Math.max(1, Math.ceil(maximum / 4))) {
    node.appendChild(shape('line', {
      x1: padding.left, x2: width - padding.right, y1: y(step), y2: y(step),
      stroke: COLORS.grid, 'stroke-width': 1,
    }));
    node.appendChild(label(padding.left - 6, y(step) + 4, String(step), { anchor: 'end' }));
  }

  const polyline = (key, color) => shape('polyline', {
    points: entries.map((entry, index) => `${x(index)},${y(entry[key])}`).join(' '),
    fill: 'none', stroke: color, 'stroke-width': 2,
    'stroke-linejoin': 'round', 'stroke-linecap': 'round',
  });

  node.appendChild(polyline('against', COLORS.loss));
  node.appendChild(polyline('for', COLORS.win));

  entries.forEach((entry, index) => {
    node.appendChild(shape('circle', {
      cx: x(index), cy: y(entry.for), r: 3, fill: COLORS.win,
    }));
  });

  node.appendChild(label(padding.left, height - 6, 'plus ancien', { anchor: 'start' }));
  node.appendChild(label(width - padding.right, height - 6, 'plus recent', { anchor: 'end' }));
  return node;
}

/**
 * Deroule du score d'une partie, point par point.
 * @param {{t: number, scores: number[]}[]} timeline
 */
export function scoreTimeline(timeline, names) {
  if (timeline.length === 0) return null;

  const width = 460;
  const height = 180;
  const padding = { top: 12, right: 12, bottom: 26, left: 28 };
  const lastPoint = timeline[timeline.length - 1];
  const maxScore = Math.max(...lastPoint.scores, 1);
  const maxTime = Math.max(lastPoint.t, 1);

  const node = svg(width, height,
    `Evolution du score : ${names[0]} ${lastPoint.scores[0]}, `
    + `${names[1]} ${lastPoint.scores[1]}.`);

  const x = (t) => padding.left + (t / maxTime) * (width - padding.left - padding.right);
  const y = (value) => height - padding.bottom
    - (value / maxScore) * (height - padding.top - padding.bottom);

  for (let step = 0; step <= maxScore; step += Math.max(1, Math.ceil(maxScore / 4))) {
    node.appendChild(shape('line', {
      x1: padding.left, x2: width - padding.right, y1: y(step), y2: y(step),
      stroke: COLORS.grid, 'stroke-width': 1,
    }));
    node.appendChild(label(padding.left - 6, y(step) + 4, String(step), { anchor: 'end' }));
  }

  // Escalier : le score reste constant entre deux points, il ne progresse pas
  // continument. Une ligne droite entre deux points mentirait sur le deroule.
  for (const side of [0, 1]) {
    let points = `${x(0)},${y(0)}`;
    let current = 0;
    for (const entry of timeline) {
      points += ` ${x(entry.t)},${y(current)}`;
      current = entry.scores[side];
      points += ` ${x(entry.t)},${y(current)}`;
    }
    node.appendChild(shape('polyline', {
      points, fill: 'none', stroke: side === 0 ? COLORS.win : COLORS.loss,
      'stroke-width': 2, 'stroke-linejoin': 'round',
    }));
  }

  node.appendChild(label(padding.left, height - 6, '0 s', { anchor: 'start' }));
  node.appendChild(label(width - padding.right, height - 6,
    `${Math.round(maxTime)} s`, { anchor: 'end' }));
  return node;
}

export function legend(items) {
  const node = document.createElement('ul');
  node.className = 'list-inline small text-body-secondary mb-0';
  for (const [text, color] of items) {
    const item = document.createElement('li');
    item.className = 'list-inline-item d-inline-flex align-items-center gap-1';

    const dot = document.createElement('span');
    dot.style.cssText = `width:.6rem;height:.6rem;border-radius:50%;background:${color};`;
    dot.setAttribute('aria-hidden', 'true');

    item.appendChild(dot);
    item.appendChild(document.createTextNode(text));
    node.appendChild(item);
  }
  return node;
}

export { COLORS };
