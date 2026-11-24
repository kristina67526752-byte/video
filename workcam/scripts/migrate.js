'use strict';
// Crée/met à jour le schéma, puis insère les catégories et réglages par défaut (sans écraser l'existant).
const fs = require('fs');
const path = require('path');
const db = require('../src/db');
const { DEFAULT_SETTINGS } = require('../src/services/settings');

const CATEGORIES = [
  ['plomberie', 'Plomberie', 'Plumbing', '🚰'],
  ['electricite', 'Électricité', 'Electrical work', '💡'],
  ['menage', 'Ménage & nettoyage', 'Cleaning', '🧹'],
  ['cours', 'Cours particuliers', 'Private tutoring', '📚'],
  ['coiffure-beaute', 'Coiffure & beauté', 'Hair & beauty', '💇'],
  ['couture', 'Couture & mode', 'Tailoring & fashion', '🧵'],
  ['mecanique', 'Mécanique auto & moto', 'Car & motorbike repair', '🔧'],
  ['menuiserie', 'Menuiserie', 'Carpentry', '🪚'],
  ['maconnerie', 'Maçonnerie & BTP', 'Masonry & construction', '🧱'],
  ['peinture', 'Peinture', 'Painting', '🎨'],
  ['climatisation', 'Climatisation & froid', 'Air-conditioning & refrigeration', '❄️'],
  ['soudure', 'Soudure & ferronnerie', 'Welding & metalwork', '⚙️'],
  ['reparation-tel', 'Réparation téléphones & PC', 'Phone & computer repair', '📱'],
  ['informatique', 'Informatique & web', 'IT & web', '💻'],
  ['design', 'Graphisme & photo', 'Design & photography', '📷'],
  ['evenementiel', 'Événementiel & traiteur', 'Events & catering', '🎉'],
  ['demenagement', 'Déménagement & transport', 'Moving & transport', '🚚'],
  ['livraison', 'Livraison & coursier', 'Delivery & errands', '🛵'],
  ['garde-enfants', "Garde d'enfants", 'Childcare', '🧸'],
  ['jardinage', 'Jardinage & entretien', 'Gardening & maintenance', '🌿'],
  ['autre', 'Autres services', 'Other services', '✨'],
];

async function migrate() {
  const sql = fs.readFileSync(path.join(__dirname, '..', 'db', 'schema.sql'), 'utf8');
  await db.query(sql);
  for (const [i, [slug, fr, en, icon]] of CATEGORIES.entries()) {
    await db.query(
      'INSERT INTO categories (slug, name_fr, name_en, icon, sort_order) VALUES ($1,$2,$3,$4,$5) ON CONFLICT (slug) DO NOTHING',
      [slug, fr, en, icon, i]
    );
  }
  for (const [key, value] of Object.entries(DEFAULT_SETTINGS)) {
    await db.query('INSERT INTO settings (key, value) VALUES ($1, $2) ON CONFLICT (key) DO NOTHING', [key, JSON.stringify(value)]);
  }
}

if (require.main === module) {
  migrate().then(() => { console.log('Migration terminée.'); return db.pool.end(); })
    .catch((e) => { console.error(e); process.exit(1); });
}
module.exports = { migrate };
