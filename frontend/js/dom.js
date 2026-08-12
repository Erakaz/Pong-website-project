/**
 * Construction du DOM sans jamais passer par innerHTML.
 *
 * C'est la brique anti-XSS du frontend : tout texte issu du serveur ou d'un
 * autre joueur (pseudo, message de chat, alias de tournoi) devient un noeud
 * texte, jamais du HTML interprete. Combine a la CSP sans `unsafe-inline`
 * (voir nginx.conf), une injection reste inerte meme si un echappement etait
 * oublie quelque part.
 *
 * Regle du projet : `innerHTML` n'apparait nulle part dans js/.
 */

/**
 * @param {string} tag       nom de balise
 * @param {object} [props]   attributs, `class`, `dataset`, `on*` gestionnaires
 * @param {...(Node|string|number|null|undefined|Array)} children
 * @returns {HTMLElement}
 */
export function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);

  for (const [key, value] of Object.entries(props || {})) {
    if (value === null || value === undefined || value === false) continue;

    if (key === 'class' || key === 'className') {
      node.className = String(value);
    } else if (key === 'dataset') {
      for (const [dataKey, dataValue] of Object.entries(value)) {
        node.dataset[dataKey] = String(dataValue);
      }
    } else if (key === 'style' && typeof value === 'object') {
      for (const [prop, propValue] of Object.entries(value)) {
        node.style.setProperty(prop, String(propValue));
      }
    } else if (key.startsWith('on') && typeof value === 'function') {
      node.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (key === 'text') {
      node.textContent = String(value);
    } else if (value === true) {
      node.setAttribute(key, '');
    } else {
      node.setAttribute(key, String(value));
    }
  }

  append(node, children);
  return node;
}

/** Ajoute des enfants en aplatissant les tableaux et en ignorant les vides. */
export function append(parent, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    parent.appendChild(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return parent;
}

/** Fragment : permet a une vue de renvoyer plusieurs noeuds racine. */
export function frag(...children) {
  return append(document.createDocumentFragment(), children);
}

/** Vide un noeud sans laisser de gestionnaires orphelins. */
export function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
  return node;
}

/** Raccourci pour un noeud texte explicite. */
export function text(value) {
  return document.createTextNode(String(value));
}

/** Icone SVG inline, dessinee a partir d'un chemin (aucune police externe). */
export function icon(pathData, { size = 16, label = null } = {}) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 16 16');
  svg.setAttribute('width', String(size));
  svg.setAttribute('height', String(size));
  svg.setAttribute('fill', 'currentColor');
  if (label) {
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', label);
  } else {
    svg.setAttribute('aria-hidden', 'true');
  }
  const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  path.setAttribute('d', pathData);
  svg.appendChild(path);
  return svg;
}
