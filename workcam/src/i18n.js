'use strict';
const dict = require('./i18n/messages');

const LANGS = ['fr', 'en'];

function translator(lang) {
  const idx = lang === 'en' ? 1 : 0;
  return function t(key, vars) {
    const entry = dict[key];
    let s = entry ? (entry[idx] || entry[0]) : key;
    if (vars) for (const [k, v] of Object.entries(vars)) s = s.split(`{${k}}`).join(String(v));
    return s;
  };
}

function pickLang(req) {
  const c = req.cookies && req.cookies.lang;
  if (LANGS.includes(c)) return c;
  if (req.user && LANGS.includes(req.user.lang)) return req.user.lang;
  const al = String(req.headers['accept-language'] || '').toLowerCase();
  return al.startsWith('en') ? 'en' : 'fr';
}

module.exports = { translator, pickLang, LANGS, dict };
