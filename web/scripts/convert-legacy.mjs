// Одноразовая конверсия: старые strings.js/body.js -> JSON для нового фронта.
import fs from 'node:fs'; import vm from 'node:vm';
const base = new URL('../../src/tjapp/static/', import.meta.url);
const ctx = { window: {} }; vm.createContext(ctx);
vm.runInContext(fs.readFileSync(new URL('strings.js', base), 'utf8'), ctx);
for (const l of ['ru', 'en']) fs.writeFileSync(new URL(`../src/i18n/legacy.${l}.json`, import.meta.url), JSON.stringify(ctx.window.STR[l], null, 1));
vm.runInContext(fs.readFileSync(new URL('body.js', base), 'utf8'), ctx);
fs.writeFileSync(new URL('../src/data/body.json', import.meta.url), JSON.stringify(ctx.window.BODY));
console.log(Object.keys(ctx.window.STR.ru).length, Object.keys(ctx.window.STR.en).length);
