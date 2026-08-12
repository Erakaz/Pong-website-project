/**
 * Rendu d'un QR code en SVG.
 *
 * S'appuie sur `qrcode-generator` (Kazuhiko Arase, licence MIT), vendorise
 * dans `vendor/qrcode/`. C'est une bibliotheque a usage unique — elle calcule
 * une matrice de modules, rien d'autre — ce qui reste dans ce que le sujet
 * autorise : « a small library that solves a simple and unique task ».
 *
 * Le fichier est en UMD, donc chargeable seulement par balise `<script>` et
 * pas par `import`. Il est injecte a la demande, uniquement sur l'ecran de
 * double authentification : les autres pages ne le telechargent jamais.
 *
 * Le QR est dessine dans le navigateur, a partir de l'URI `otpauth://` recue
 * du serveur. Le secret ne quitte donc jamais l'application — le faire generer
 * par une API de QR code en ligne reviendrait a l'envoyer a un tiers.
 */

const SCRIPT_URL = '/vendor/qrcode/qrcode.js';
const SVG_NS = 'http://www.w3.org/2000/svg';

let loading = null;

function loadLibrary() {
  if (window.qrcode) return Promise.resolve(window.qrcode);
  if (loading) return loading;

  loading = new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = SCRIPT_URL;
    script.addEventListener('load', () => {
      if (window.qrcode) resolve(window.qrcode);
      else reject(new Error('Bibliotheque QR indisponible.'));
    });
    script.addEventListener('error', () => reject(new Error('Chargement du QR code impossible.')));
    document.head.appendChild(script);
  });
  return loading;
}

/**
 * @param {string} text        contenu encode (ici l'URI otpauth://)
 * @param {number} [size]      cote du SVG en pixels
 * @returns {Promise<SVGElement>}
 */
export async function renderQr(text, { size = 208, label = 'QR code de configuration' } = {}) {
  const qrcode = await loadLibrary();

  // Type 0 = choix automatique de la version selon la longueur du contenu.
  // Correction d'erreur « M » : le compromis habituel entre densite et
  // tolerance aux reflets de l'ecran.
  const generator = qrcode(0, 'M');
  generator.addData(text);
  generator.make();

  const count = generator.getModuleCount();
  const quiet = 2;                       // marge blanche obligatoire autour du code
  const total = count + quiet * 2;

  const svg = document.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('viewBox', `0 0 ${total} ${total}`);
  svg.setAttribute('width', String(size));
  svg.setAttribute('height', String(size));
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', label);
  svg.setAttribute('shape-rendering', 'crispEdges');

  const background = document.createElementNS(SVG_NS, 'rect');
  background.setAttribute('width', String(total));
  background.setAttribute('height', String(total));
  background.setAttribute('fill', '#ffffff');
  svg.appendChild(background);

  // Un seul `path` pour toute la matrice : quelques centaines de `rect`
  // alourdiraient inutilement le DOM.
  let path = '';
  for (let row = 0; row < count; row += 1) {
    for (let column = 0; column < count; column += 1) {
      if (generator.isDark(row, column)) {
        path += `M${column + quiet} ${row + quiet}h1v1h-1z`;
      }
    }
  }

  const shape = document.createElementNS(SVG_NS, 'path');
  shape.setAttribute('d', path);
  shape.setAttribute('fill', '#000000');
  svg.appendChild(shape);

  return svg;
}
