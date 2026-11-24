'use strict';
// Usage : node scripts/create-admin.js 6XXXXXXXX "MotDePasseSolide" "Nom Prénom"
// Crée un compte administrateur, ou promeut un compte existant.
const bcrypt = require('bcryptjs');
const db = require('../src/db');
const { normalizePhone } = require('../src/services/phone');

(async () => {
  const [rawPhone, password, name = 'Administrateur'] = process.argv.slice(2);
  const phone = normalizePhone(rawPhone || '');
  if (!phone || !password || password.length < 10) {
    console.error('Usage : node scripts/create-admin.js 6XXXXXXXX "MotDePasse(10+ caractères)" "Nom"');
    process.exit(1);
  }
  const hash = await bcrypt.hash(password, 12);
  await db.query(
    `INSERT INTO users (role, full_name, phone, password_hash, phone_verified, photo_status)
     VALUES ('admin', $1, $2, $3, TRUE, 'approved')
     ON CONFLICT (phone) DO UPDATE SET role='admin', password_hash=EXCLUDED.password_hash, is_banned=FALSE`,
    [name, phone, hash]
  );
  console.log(`Administrateur prêt : ${phone}`);
  await db.pool.end();
})().catch((e) => { console.error(e); process.exit(1); });
