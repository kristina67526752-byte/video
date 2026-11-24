'use strict';
const db = require('../db');

async function loadUser(req, res, next) {
  req.user = null;
  if (req.session && req.session.userId) {
    try {
      const u = await db.one('SELECT * FROM users WHERE id=$1', [req.session.userId]);
      if (u && !u.is_banned) {
        req.user = u;
        if (!u.last_seen_at || Date.now() - new Date(u.last_seen_at).getTime() > 5 * 60000) {
          db.query('UPDATE users SET last_seen_at=now() WHERE id=$1', [u.id]).catch(() => {});
        }
      } else {
        req.session.userId = null;
      }
    } catch (e) { return next(e); }
  }
  next();
}

function requireAuth(req, res, next) {
  if (!req.user) {
    req.session.returnTo = req.originalUrl;
    return res.redirect('/login');
  }
  next();
}

function requireRole(...roles) {
  return (req, res, next) => {
    if (!req.user) return requireAuth(req, res, next);
    if (!roles.includes(req.user.role) && req.user.role !== 'admin') {
      const err = new Error('Forbidden'); err.status = 403; return next(err);
    }
    next();
  };
}

function requireAdmin(req, res, next) {
  if (!req.user) return requireAuth(req, res, next);
  if (req.user.role !== 'admin') { const err = new Error('Forbidden'); err.status = 403; return next(err); }
  next();
}

/** Exige une photo de profil validée (automatiquement ou manuellement). */
function requireApprovedPhoto(req, res, next) {
  if (req.user && (req.user.photo_status === 'approved' || req.user.role === 'admin')) return next();
  req.flash('warning', 'flash.photo_required');
  return res.redirect('/account/photo');
}

module.exports = { loadUser, requireAuth, requireRole, requireAdmin, requireApprovedPhoto };
