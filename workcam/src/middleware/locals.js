'use strict';
const config = require('../config');
const db = require('../db');
const { translator, pickLang } = require('../i18n');
const { formatPhone } = require('../services/phone');

function formatPrice(n) {
  if (n === null || n === undefined || n === '') return '';
  return `${Number(n).toLocaleString('fr-FR').replace(/ | /g, ' ')} FCFA`;
}

function timeAgo(date, t) {
  const s = Math.max(1, Math.floor((Date.now() - new Date(date).getTime()) / 1000));
  if (s < 60) return t('time.now');
  if (s < 3600) return t('time.minutes', { n: Math.floor(s / 60) });
  if (s < 86400) return t('time.hours', { n: Math.floor(s / 3600) });
  return t('time.days', { n: Math.floor(s / 86400) });
}

function flashMiddleware(req, res, next) {
  req.flash = (type, key, vars) => {
    req.session.flash = req.session.flash || [];
    req.session.flash.push({ type, key, vars });
  };
  res.locals.flashes = req.session.flash || [];
  req.session.flash = [];
  next();
}

async function locals(req, res, next) {
  const lang = pickLang(req);
  const t = translator(lang);
  req.lang = lang; req.t = t;
  Object.assign(res.locals, {
    lang, t, user: req.user, config, path: req.path, query: req.query,
    formatPrice, formatPhone, timeAgo: (d) => timeAgo(d, t),
    catName: (c) => (c ? (lang === 'en' ? c.name_en : c.name_fr) : ''),
    unread: 0, pendingAdmin: 0,
  });
  if (req.user && req.accepts('html') && req.method === 'GET') {
    try {
      const r = await db.one(
        `SELECT count(*)::int AS n FROM messages m JOIN conversations c ON c.id=m.conversation_id
         WHERE (c.user_low=$1 OR c.user_high=$1) AND m.sender_id<>$1 AND m.read_at IS NULL`, [req.user.id]);
      res.locals.unread = r.n;
      if (req.user.role === 'admin') {
        const a = await db.one(`SELECT (SELECT count(*) FROM photo_reviews WHERE status='pending')
          + (SELECT count(*) FROM reports WHERE status='open') AS n`);
        res.locals.pendingAdmin = Number(a.n);
      }
    } catch (e) { /* non bloquant */ }
  }
  next();
}

module.exports = { locals, flashMiddleware, formatPrice };
