

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


export async function renderQr(text, { size = 208, label = 'QR code de configuration' } = {}) {
  const qrcode = await loadLibrary();


  const generator = qrcode(0, 'M');
  generator.addData(text);
  generator.make();

  const count = generator.getModuleCount();
  const quiet = 2;
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
