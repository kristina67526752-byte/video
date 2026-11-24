'use strict';
const express = require('express');
const rateLimit = require('express-rate-limit');
const db = require('../db');
const { requireAuth } = require('../middleware/auth');
const { postMessage } = require('../services/conversations');

const router = express.Router();
const sendLimiter = rateLimit({
  windowMs: 60 * 1000, limit: 20, standardHeaders: 'draft-7', legacyHeaders: false,
  keyGenerator: (req) => `u${req.user ? req.user.id : req.ip}`,
  validate: { keyGeneratorIpFallback: false },
  handler: (req, res, next) => { const e = new Error('rate'); e.status = 429; next(e); },
});

async function loadConversation(req) {
  const id = parseInt(req.params.id, 10) || 0;
  const c = await db.one(`SELECT c.*,
      CASE WHEN c.user_low=$2 THEN c.user_high ELSE c.user_low END AS other_id
    FROM conversations c WHERE c.id=$1 AND (c.user_low=$2 OR c.user_high=$2)`, [id, req.user.id]);
  return c;
}

const serialize = (m, me) => ({ id: m.id, body: m.body, mine: m.sender_id === me, at: m.created_at });

router.get('/messages', requireAuth, async (req, res, next) => {
  try {
    const convs = await db.many(`SELECT c.id, c.last_message_at, u.id AS other_id, u.full_name, u.photo_path, u.role,
        l.title AS listing_title, q.title AS request_title,
        (SELECT body FROM messages m WHERE m.conversation_id=c.id ORDER BY m.id DESC LIMIT 1) AS last_body,
        (SELECT count(*)::int FROM messages m WHERE m.conversation_id=c.id AND m.sender_id<>$1 AND m.read_at IS NULL) AS unread
      FROM conversations c
      JOIN users u ON u.id = CASE WHEN c.user_low=$1 THEN c.user_high ELSE c.user_low END
      LEFT JOIN listings l ON l.id=c.listing_id LEFT JOIN client_requests q ON q.id=c.request_id
      WHERE (c.user_low=$1 OR c.user_high=$1)
        AND (EXISTS (SELECT 1 FROM messages m WHERE m.conversation_id=c.id))
      ORDER BY c.last_message_at DESC`, [req.user.id]);
    res.render('messages/inbox', { title: res.locals.t('nav.messages'), convs });
  } catch (e) { next(e); }
});

router.get('/messages/:id', requireAuth, async (req, res, next) => {
  try {
    const c = await loadConversation(req);
    if (!c) return next();
    const other = await db.one('SELECT id, full_name, photo_path, role, headline, city, is_banned FROM users WHERE id=$1', [c.other_id]);
    const messages = await db.many('SELECT * FROM messages WHERE conversation_id=$1 ORDER BY id DESC LIMIT 200', [c.id]);
    messages.reverse();
    await db.query('UPDATE messages SET read_at=now() WHERE conversation_id=$1 AND sender_id<>$2 AND read_at IS NULL', [c.id, req.user.id]);
    const listing = c.listing_id ? await db.one('SELECT id, title FROM listings WHERE id=$1', [c.listing_id]) : null;
    const request = c.request_id ? await db.one('SELECT id, title FROM client_requests WHERE id=$1', [c.request_id]) : null;
    res.render('messages/thread', { title: other.full_name, c, other, messages, listing, request });
  } catch (e) { next(e); }
});

router.post('/messages/:id', requireAuth, sendLimiter, async (req, res, next) => {
  try {
    const c = await loadConversation(req);
    if (!c) return next();
    const other = await db.one('SELECT is_banned FROM users WHERE id=$1', [c.other_id]);
    const body = String(req.body.body || '').trim().slice(0, 2000);
    const wantsJson = req.xhr || String(req.headers.accept || '').includes('application/json');
    if (!body || other.is_banned) {
      if (wantsJson) return res.status(422).json({ error: 'empty' });
      return res.redirect(`/messages/${c.id}`);
    }
    const m = await postMessage(c.id, req.user.id, body);
    if (wantsJson) return res.json({ message: serialize(m, req.user.id) });
    res.redirect(`/messages/${c.id}#m${m.id}`);
  } catch (e) { next(e); }
});

/* Polling léger (toutes les 5 s) : pas de WebSocket nécessaire, fonctionne bien en 3G. */
router.get('/api/messages/:id', requireAuth, async (req, res, next) => {
  try {
    const c = await loadConversation(req);
    if (!c) return res.status(404).json({ error: 'not_found' });
    const after = parseInt(req.query.after, 10) || 0;
    const rows = await db.many('SELECT * FROM messages WHERE conversation_id=$1 AND id>$2 ORDER BY id LIMIT 100', [c.id, after]);
    if (rows.some((m) => m.sender_id !== req.user.id)) {
      await db.query('UPDATE messages SET read_at=now() WHERE conversation_id=$1 AND sender_id<>$2 AND read_at IS NULL', [c.id, req.user.id]);
    }
    res.json({ messages: rows.map((m) => serialize(m, req.user.id)) });
  } catch (e) { next(e); }
});

module.exports = router;
