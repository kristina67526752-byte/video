'use strict';
const path = require('path');
const fs = require('fs');
const express = require('express');
const session = require('express-session');
const PgSession = require('connect-pg-simple')(session);
const helmet = require('helmet');
const cookieParser = require('cookie-parser');
const config = require('./config');
const db = require('./db');
const { loadUser } = require('./middleware/auth');
const { csrfProtection } = require('./middleware/csrf');
const { locals, flashMiddleware } = require('./middleware/locals');

function createApp() {
  const app = express();
  app.set('view engine', 'ejs');
  app.set('views', path.join(__dirname, 'views'));
  app.set('trust proxy', 1); // derrière Caddy / Nginx
  app.disable('x-powered-by');

  for (const d of ['avatars', 'pending']) fs.mkdirSync(path.join(config.uploadDir, d), { recursive: true });

  app.use(helmet({
    contentSecurityPolicy: {
      directives: {
        defaultSrc: ["'self'"],
        imgSrc: ["'self'", 'data:', 'blob:'],
        scriptSrc: ["'self'"],
        styleSrc: ["'self'"],
        formAction: ["'self'"],
        frameAncestors: ["'none'"],
        upgradeInsecureRequests: config.isProd ? [] : null,
      },
    },
    crossOriginEmbedderPolicy: false,
  }));

  app.use('/static', express.static(path.join(__dirname, '..', 'public'), { maxAge: config.isProd ? '7d' : 0 }));
  app.use('/uploads/avatars', express.static(path.join(config.uploadDir, 'avatars'), { maxAge: '30d', fallthrough: false }));
  app.get('/favicon.ico', (req, res) => res.redirect(301, '/static/img/logo.svg'));

  app.use(express.urlencoded({ extended: false, limit: '100kb' }));
  app.use(express.json({ limit: '100kb' }));
  app.use(cookieParser());
  app.use(session({
    store: new PgSession({ pool: db.pool, tableName: 'session', createTableIfMissing: false }),
    name: 'wc.sid',
    secret: config.sessionSecret,
    resave: false,
    saveUninitialized: false,
    rolling: true,
    cookie: { httpOnly: true, sameSite: 'lax', secure: config.isProd, maxAge: 30 * 24 * 3600 * 1000 },
  }));

  app.use(loadUser);
  app.use(flashMiddleware);
  app.use(csrfProtection);
  app.use(locals);

  app.use(require('./routes/public'));
  app.use(require('./routes/auth'));
  app.use(require('./routes/account'));
  app.use(require('./routes/listings'));
  app.use(require('./routes/requests'));
  app.use(require('./routes/messages'));
  app.use(require('./routes/payments'));
  app.use('/admin', require('./routes/admin'));

  app.use((req, res) => res.status(404).render('pages/error', { title: res.locals.t('error.404'), code: 404, message: res.locals.t('error.404') }));

  // eslint-disable-next-line no-unused-vars
  app.use((err, req, res, next) => {
    const status = err.status || (err.code === 'LIMIT_FILE_SIZE' ? 413 : 500);
    if (status >= 500) console.error(err);
    const t = res.locals.t || ((k) => k);
    let msg = t('error.500');
    if (status === 403) msg = err.code === 'csrf' ? t('error.csrf') : t('error.403');
    if (status === 404) msg = t('error.404');
    if (status === 413) msg = t('error.too_large');
    if (status === 429) msg = t('error.rate');
    if (req.path.startsWith('/api/') || req.xhr) return res.status(status).json({ error: msg });
    res.status(status).render('pages/error', { title: msg, code: status, message: msg });
  });

  return app;
}

module.exports = { createApp };
