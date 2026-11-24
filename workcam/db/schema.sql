-- Work.cam — schéma PostgreSQL (idempotent : peut être rejoué sans perte de données)

CREATE TABLE IF NOT EXISTS users (
  id              SERIAL PRIMARY KEY,
  role            TEXT NOT NULL CHECK (role IN ('client','provider','admin')),
  full_name       TEXT NOT NULL,
  phone           TEXT NOT NULL UNIQUE,            -- format E.164 : +2376XXXXXXXX
  email           TEXT UNIQUE,
  password_hash   TEXT NOT NULL,
  city            TEXT,
  headline        TEXT,                            -- prestataire : métier en une ligne
  bio             TEXT,
  experience      TEXT,
  availability    TEXT,
  price_note      TEXT,                            -- tarifs indicatifs
  lang            TEXT NOT NULL DEFAULT 'fr',
  photo_path      TEXT,                            -- photo publique validée
  photo_status    TEXT NOT NULL DEFAULT 'none' CHECK (photo_status IN ('none','approved','pending_review','rejected')),
  photo_failures  INTEGER NOT NULL DEFAULT 0,      -- échecs consécutifs de la détection automatique
  phone_verified  BOOLEAN NOT NULL DEFAULT FALSE,
  is_banned       BOOLEAN NOT NULL DEFAULT FALSE,
  last_seen_at    TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS categories (
  id           SERIAL PRIMARY KEY,
  slug         TEXT NOT NULL UNIQUE,
  name_fr      TEXT NOT NULL,
  name_en      TEXT NOT NULL,
  icon         TEXT NOT NULL DEFAULT '🛠️',
  listing_fee  INTEGER,                            -- NULL = tarif global ; sinon tarif spécifique (FCFA)
  sort_order   INTEGER NOT NULL DEFAULT 0,
  is_active    BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS listings (
  id            SERIAL PRIMARY KEY,
  provider_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  category_id   INTEGER NOT NULL REFERENCES categories(id),
  title         TEXT NOT NULL,
  description   TEXT NOT NULL,
  city          TEXT NOT NULL,
  district      TEXT,                              -- quartier
  price_min     INTEGER,
  price_max     INTEGER,
  price_unit    TEXT NOT NULL DEFAULT 'job' CHECK (price_unit IN ('job','hour','day','month')),
  status        TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','pending_payment','active','expired','suspended')),
  is_free_promo BOOLEAN NOT NULL DEFAULT FALSE,
  published_at  TIMESTAMPTZ,
  expires_at    TIMESTAMPTZ,
  views         INTEGER NOT NULL DEFAULT 0,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS listings_search_idx ON listings (status, category_id, city);
CREATE INDEX IF NOT EXISTS listings_provider_idx ON listings (provider_id);

CREATE TABLE IF NOT EXISTS client_requests (
  id          SERIAL PRIMARY KEY,
  client_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  category_id INTEGER NOT NULL REFERENCES categories(id),
  title       TEXT NOT NULL,
  description TEXT NOT NULL,
  city        TEXT NOT NULL,
  district    TEXT,
  budget      INTEGER,
  status      TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','closed','suspended')),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS requests_search_idx ON client_requests (status, category_id, city);

CREATE TABLE IF NOT EXISTS request_responses (
  id          SERIAL PRIMARY KEY,
  request_id  INTEGER NOT NULL REFERENCES client_requests(id) ON DELETE CASCADE,
  provider_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  message     TEXT NOT NULL,
  price       INTEGER,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (request_id, provider_id)
);

CREATE TABLE IF NOT EXISTS conversations (
  id              SERIAL PRIMARY KEY,
  user_low        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,  -- toujours le plus petit id
  user_high       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  listing_id      INTEGER REFERENCES listings(id) ON DELETE SET NULL,
  request_id      INTEGER REFERENCES client_requests(id) ON DELETE SET NULL,
  last_message_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (user_low < user_high),
  UNIQUE (user_low, user_high)
);

CREATE TABLE IF NOT EXISTS messages (
  id              SERIAL PRIMARY KEY,
  conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  sender_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  body            TEXT NOT NULL,
  read_at         TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS messages_conv_idx ON messages (conversation_id, id);

CREATE TABLE IF NOT EXISTS payments (
  id                 SERIAL PRIMARY KEY,
  user_id            INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  listing_id         INTEGER REFERENCES listings(id) ON DELETE SET NULL,
  amount             INTEGER NOT NULL,
  currency           TEXT NOT NULL DEFAULT 'XAF',
  gateway            TEXT NOT NULL,                 -- 'campay' | 'simulation'
  operator           TEXT NOT NULL CHECK (operator IN ('orange','mtn')),
  phone              TEXT NOT NULL,
  external_reference TEXT NOT NULL UNIQUE,          -- notre référence (UUID)
  gateway_reference  TEXT,                          -- référence de l'agrégateur
  ussd_code          TEXT,
  status             TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','successful','failed')),
  failure_reason     TEXT,
  raw                JSONB,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS payments_status_idx ON payments (status, created_at);

CREATE TABLE IF NOT EXISTS photo_reviews (
  id           SERIAL PRIMARY KEY,
  user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  file_name    TEXT NOT NULL,                       -- fichier dans uploads/pending (non public)
  auto_reason  TEXT,                                -- raison du rejet automatique
  user_note    TEXT,
  status       TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected')),
  admin_note   TEXT,
  reviewed_by  INTEGER REFERENCES users(id),
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  reviewed_at  TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS reports (
  id          SERIAL PRIMARY KEY,
  reporter_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
  target_type TEXT NOT NULL CHECK (target_type IN ('listing','user','request')),
  target_id   INTEGER NOT NULL,
  reason      TEXT NOT NULL,
  status      TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','closed')),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS otp_codes (
  phone       TEXT PRIMARY KEY,
  code_hash   TEXT NOT NULL,
  attempts    INTEGER NOT NULL DEFAULT 0,
  expires_at  TIMESTAMPTZ NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS settings (
  key   TEXT PRIMARY KEY,
  value JSONB NOT NULL
);

-- Sessions (connect-pg-simple)
CREATE TABLE IF NOT EXISTS "session" (
  "sid"    VARCHAR NOT NULL PRIMARY KEY,
  "sess"   JSON NOT NULL,
  "expire" TIMESTAMP(6) NOT NULL
);
CREATE INDEX IF NOT EXISTS "IDX_session_expire" ON "session" ("expire");
