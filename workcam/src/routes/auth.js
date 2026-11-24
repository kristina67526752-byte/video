'use strict';
const express = require('express');
const crypto = require('crypto');
const bcrypt = require('bcryptjs');
const rateLimit = require('express-rate-limit');
const db = require('../db');
const config = require('../config');
const { normalizePhone } = require('../services/phone');
const { sendSms } = require('../services/sms');
const { requireAuth } = require('../middleware/auth');

const router = express.Router();

const authLimiter = rateLimit({
  windowMs: 15 * 60 * 1000, limit: 20, standardHeaders: 'draft-7', legacyHeaders: false,
  handler: (req, res, next) => { const e = new Error('rate'); e.status = 429; next(e); },
});
const otpLimiter = rateLimit({
  windowMs: 60 * 60 * 1000, limit: 6, standardHeaders: 'draft-7', legacyHeaders: false,
  handler: (req, res, next) => { const e = new Error('rate'); e.status = 429; next(e); },
});

// Empreinte factice : la comparaison prend le même temps que le compte existe ou non.
const DUMMY_HASH = bcrypt.hashSync('workcam-dummy-password', 12);
const EMAIL_RE = /^[^\s@]{1,64}@[^\s@]{1,190}\.[^\s@]{2,20}$/;

function login(req, user) {
  return new Promise((resolve, reject) => {
    const returnTo = req.session.returnTo;
    req.session.regenerate((err) => {
      if (err) return reject(err);
      req.session.userId = user.id;
      req.session.save((e) => (e ? reject(e) : resolve(returnTo)));
    });
  });
}

async function sendOtp(phone, t) {
  const code = String(crypto.randomInt(100000, 1000000));
  const hash = crypto.createHash('sha256').update(`${phone}:${code}`).digest('hex');
  await db.query(
    `INSERT INTO otp_codes (phone, code_hash, attempts, expires_at) VALUES ($1,$2,0, now() + interval '10 minutes')
     ON CONFLICT (phone) DO UPDATE SET code_hash=EXCLUDED.code_hash, attempts=0, expires_at=EXCLUDED.expires_at, created_at=now()`,
    [phone, hash]
  );
  await sendSms(phone, t('sms.code', { code }));
}

async function checkOtp(phone, code) {
  const row = await db.one('SELECT * FROM otp_codes WHERE phone=$1', [phone]);
  if (!row || new Date(row.expires_at) < new Date() || row.attempts >= 5) return false;
  const hash = crypto.createHash('sha256').update(`${phone}:${String(code).trim()}`).digest('hex');
  if (hash !== row.code_hash) {
    await db.query('UPDATE otp_codes SET attempts = attempts + 1 WHERE phone=$1', [phone]);
    return false;
  }
  await db.query('DELETE FROM otp_codes WHERE phone=$1', [phone]);
  return true;
}

/* ---------- Inscription ---------- */
router.get('/register', (req, res) => {
  if (req.user) return res.redirect('/account');
  res.render('auth/register', { title: res.locals.t('auth.register_title'), form: { role: req.query.role === 'provider' ? 'provider' : 'client' }, errors: {} });
});

router.post('/register', authLimiter, async (req, res, next) => {
  try {
    const t = res.locals.t;
    const form = {
      role: req.body.role === 'provider' ? 'provider' : 'client',
      full_name: String(req.body.full_name || '').trim().slice(0, 80),
      phone: String(req.body.phone || '').trim(),
      email: String(req.body.email || '').trim().toLowerCase().slice(0, 200),
      city: String(req.body.city || ''),
    };
    const password = String(req.body.password || '');
    const errors = {};
    const phone = normalizePhone(form.phone);
    if (form.full_name.length < 3) errors.full_name = t('err.name');
    if (!phone) errors.phone = t('err.phone');
    if (form.email && !EMAIL_RE.test(form.email)) errors.email = t('err.email');
    if (!config.cities.includes(form.city)) errors.city = t('err.city');
    if (password.length < 8) errors.password = t('err.password');
    if (password !== String(req.body.password2 || '')) errors.password2 = t('err.password_match');
    if (req.body.accept !== 'on') errors.accept = t('err.accept');
    if (!errors.phone && await db.one('SELECT 1 FROM users WHERE phone=$1', [phone])) errors.phone = t('err.phone_taken');
    if (form.email && !errors.email && await db.one('SELECT 1 FROM users WHERE email=$1', [form.email])) errors.email = t('err.email_taken');
    if (Object.keys(errors).length) {
      return res.status(422).render('auth/register', { title: t('auth.register_title'), form, errors });
    }
    const hash = await bcrypt.hash(password, 12);
    const user = await db.one(
      `INSERT INTO users (role, full_name, phone, email, password_hash, city, lang, phone_verified)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING *`,
      [form.role, form.full_name, phone, form.email || null, hash, form.city, req.lang, !config.phoneVerification]
    );
    await login(req, user);
    if (config.phoneVerification) {
      await sendOtp(phone, t);
      return res.redirect('/verify-phone');
    }
    req.flash('success', 'flash.welcome', { name: user.full_name.split(' ')[0] });
    res.redirect('/account/photo');
  } catch (e) { next(e); }
});

/* ---------- Vérification du numéro (si PHONE_VERIFICATION=on) ---------- */
router.get('/verify-phone', requireAuth, (req, res) => {
  if (req.user.phone_verified) return res.redirect('/account');
  res.render('auth/verify', { title: res.locals.t('auth.verify_title'), error: null });
});

router.post('/verify-phone', requireAuth, authLimiter, async (req, res, next) => {
  try {
    if (await checkOtp(req.user.phone, req.body.code)) {
      await db.query('UPDATE users SET phone_verified=TRUE WHERE id=$1', [req.user.id]);
      req.flash('success', 'flash.phone_verified');
      return res.redirect('/account/photo');
    }
    res.status(422).render('auth/verify', { title: res.locals.t('auth.verify_title'), error: res.locals.t('err.code') });
  } catch (e) { next(e); }
});

router.post('/verify-phone/resend', requireAuth, otpLimiter, async (req, res, next) => {
  try {
    await sendOtp(req.user.phone, res.locals.t);
    req.flash('info', 'flash.code_sent');
    res.redirect('/verify-phone');
  } catch (e) { next(e); }
});

/* ---------- Connexion ---------- */
router.get('/login', (req, res) => {
  if (req.user) return res.redirect('/account');
  res.render('auth/login', { title: res.locals.t('auth.login_title'), phone: '', error: null });
});

router.post('/login', authLimiter, async (req, res, next) => {
  try {
    const phone = normalizePhone(req.body.phone);
    const user = phone ? await db.one('SELECT * FROM users WHERE phone=$1', [phone]) : null;
    // Comparaison toujours effectuée pour ne pas révéler l'existence du compte par le temps de réponse.
    const ok = await bcrypt.compare(String(req.body.password || ''), user ? user.password_hash : DUMMY_HASH);
    if (!user || !ok) {
      return res.status(401).render('auth/login', { title: res.locals.t('auth.login_title'), phone: req.body.phone || '', error: res.locals.t('err.login') });
    }
    if (user.is_banned) {
      return res.status(403).render('auth/login', { title: res.locals.t('auth.login_title'), phone: req.body.phone || '', error: res.locals.t('err.banned') });
    }
    const returnTo = await login(req, user);
    if (user.lang) res.cookie('lang', user.lang, { maxAge: 365 * 24 * 3600 * 1000, sameSite: 'lax', secure: config.isProd });
    res.redirect(returnTo && returnTo.startsWith('/') && !returnTo.startsWith('//') ? returnTo : (user.role === 'admin' ? '/admin' : '/account'));
  } catch (e) { next(e); }
});

router.post('/logout', (req, res) => {
  req.session.destroy(() => { res.clearCookie('wc.sid'); res.redirect('/'); });
});

/* ---------- Mot de passe oublié (code par SMS) ---------- */
router.get('/forgot', (req, res) => res.render('auth/forgot', { title: res.locals.t('auth.forgot_title'), step: 'phone', phone: '', error: null }));

router.post('/forgot', otpLimiter, async (req, res, next) => {
  try {
    const phone = normalizePhone(req.body.phone);
    if (phone && await db.one('SELECT 1 FROM users WHERE phone=$1 AND NOT is_banned', [phone])) await sendOtp(phone, res.locals.t);
    // Même réponse que le compte existe ou non.
    res.render('auth/forgot', { title: res.locals.t('auth.forgot_title'), step: 'code', phone: req.body.phone || '', error: null });
  } catch (e) { next(e); }
});

router.post('/reset', authLimiter, async (req, res, next) => {
  try {
    const t = res.locals.t;
    const phone = normalizePhone(req.body.phone);
    const password = String(req.body.password || '');
    const render = (error) => res.status(422).render('auth/forgot', { title: t('auth.forgot_title'), step: 'code', phone: req.body.phone || '', error });
    if (password.length < 8) return render(t('err.password'));
    if (!phone || !(await checkOtp(phone, req.body.code))) return render(t('err.code'));
    const hash = await bcrypt.hash(password, 12);
    await db.query('UPDATE users SET password_hash=$2, phone_verified=TRUE WHERE phone=$1', [phone, hash]);
    // Déconnecte toutes les sessions existantes de cet utilisateur.
    await db.query("DELETE FROM session WHERE (sess->>'userId')::text = (SELECT id::text FROM users WHERE phone=$1)", [phone]);
    req.flash('success', 'flash.password_reset');
    res.redirect('/login');
  } catch (e) { next(e); }
});

module.exports = router;
