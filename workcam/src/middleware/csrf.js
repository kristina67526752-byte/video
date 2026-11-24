'use strict';
const crypto = require('crypto');

function ensureToken(req) {
  if (!req.session.csrf) req.session.csrf = crypto.randomBytes(24).toString('hex');
  return req.session.csrf;
}

function safeEqual(a, b) {
  const x = Buffer.from(String(a || '')); const y = Buffer.from(String(b || ''));
  return x.length === y.length && crypto.timingSafeEqual(x, y);
}

/** Vérifie le jeton CSRF des requêtes modifiantes. Les formulaires multipart sont vérifiés après multer. */
function csrfProtection(req, res, next) {
  res.locals.csrfToken = ensureToken(req);
  if (['GET', 'HEAD', 'OPTIONS'].includes(req.method)) return next();
  if (req.path.startsWith('/webhooks/')) return next();
  if (String(req.headers['content-type'] || '').startsWith('multipart/form-data')) return next();
  return verify(req, res, next);
}

function verify(req, res, next) {
  const token = (req.body && req.body._csrf) || req.headers['x-csrf-token'];
  if (!safeEqual(token, req.session.csrf)) {
    const err = new Error('CSRF'); err.status = 403; err.code = 'csrf';
    return next(err);
  }
  next();
}

module.exports = { csrfProtection, verifyCsrf: verify };
