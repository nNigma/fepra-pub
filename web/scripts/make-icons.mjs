// SVG -> PNG иконки PWA (any 192/512, maskable 512, apple-touch 180). Запуск: npm run icons
import sharp from 'sharp';
import fs from 'node:fs';

const G = '#0f6e56';
// гриф с двумя блинами, внутри «безопасной зоны» (80% центра) — годится и для maskable
const glyph = `
  <g fill="#fff">
    <rect x="156" y="236" width="200" height="40" rx="14"/>
    <rect x="112" y="176" width="44" height="160" rx="14"/>
    <rect x="356" y="176" width="44" height="160" rx="14"/>
    <rect x="76" y="206" width="36" height="100" rx="12"/>
    <rect x="400" y="206" width="36" height="100" rx="12"/>
  </g>`;
const svg = (rounded) => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <rect width="512" height="512" ${rounded ? 'rx="112"' : ''} fill="${G}"/>${glyph}</svg>`;

fs.mkdirSync('public', { recursive: true });
fs.writeFileSync('public/icon.svg', svg(true));
const png = (s, size, out) => sharp(Buffer.from(s)).resize(size, size).png().toFile(out);
await png(svg(true), 192, 'public/icon-192.png');
await png(svg(true), 512, 'public/icon-512.png');
await png(svg(false), 512, 'public/icon-maskable-512.png');
await png(svg(false), 180, 'public/apple-touch-icon.png');
console.log('icons ok');
