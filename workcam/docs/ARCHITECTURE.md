# Architecture de Work.cam

## Choix techniques

| Élément | Choix | Pourquoi |
|---|---|---|
| Serveur | **Node.js 22 + Express** | Simple, rapide, une seule langue (JavaScript) pour tout le projet |
| Pages | **Rendu serveur (EJS)** + un petit script JS | Pages légères (≈ 30 Ko hors photos), rapides en 3G et sur téléphones d'entrée de gamme. Le site marche même si JavaScript est désactivé. |
| Base de données | **PostgreSQL 16** | Robuste, transactions fiables pour les paiements |
| Sessions | Stockées en base (`connect-pg-simple`) | Survivent aux redémarrages |
| Photos | Disque du serveur (`uploads/`), ré-encodées en WebP 480×480 | Gratuit. Migration vers S3/Cloudinary possible plus tard |
| Détection de visage | **Modèle local** SSD MobileNet (TensorFlow.js/WebAssembly) — Google Vision en option | Gratuit, aucune photo envoyée à un tiers |
| Paiement | **CamPay** (MTN MoMo + Orange Money) — passerelle « simulation » pour les tests | API REST simple, couvre les deux opérateurs |
| HTTPS | **Caddy** | Certificat Let's Encrypt automatique |
| Déploiement | **Docker Compose** sur un VPS | Une commande pour tout lancer |

Pourquoi pas une application React/Next.js séparée ? Pour un MVP au Cameroun, la majorité des visiteurs seront sur mobile avec une connexion variable. Le rendu serveur donne un premier affichage plus rapide, moins de code à maintenir et un seul serveur à héberger. Une application mobile ou une API JSON pourront être ajoutées ensuite en réutilisant les mêmes services (`src/services/`).

## Schéma de la base de données

Fichier complet : [`db/schema.sql`](../db/schema.sql).

```
users ─────────────┬──< listings >──── categories
 (client/prestataire/admin)   │
 │                 │          └──< payments
 │                 ├──< client_requests >── categories
 │                 │          └──< request_responses (1 par prestataire et par demande)
 │                 ├──< conversations (1 par paire d'utilisateurs) ──< messages
 │                 ├──< photo_reviews (validation manuelle)
 │                 └──< reports (signalements)
settings (clé → valeur JSON : tarifs, promotion)
otp_codes (codes SMS), session (sessions)
```

Points clés :
- `users.phone` est unique, au format `+2376XXXXXXXX`. `photo_status` : `none`, `approved`, `pending_review`, `rejected`.
- `listings.status` : `draft` (masquée) → `pending_payment` → `active` → `expired` ; `suspended` = décision de l'admin.
- `listings.expires_at` : fin de visibilité. Une tâche passe les annonces échues en `expired` toutes les 10 minutes.
- `categories.listing_fee` : tarif propre à une catégorie (NULL = tarif global).
- `payments.external_reference` (notre UUID) et `gateway_reference` (référence CamPay) sont uniques. Un paiement ne passe qu'une fois de `pending` à `successful`/`failed` (verrou `FOR UPDATE`).
- `settings` : `listing_fee`, `listing_duration_days`, `promo_enabled`, `promo_end_date`, `promo_quota`, `promo_used`, `promo_per_provider`.

## Routes principales

### Public
| Méthode | Route | Rôle |
|---|---|---|
| GET | `/` | Accueil : recherche, catégories, dernières annonces |
| GET | `/services?q=&category=&city=&sort=&page=` | Recherche d'annonces |
| GET | `/listings/:id` | Détail d'une annonce |
| GET | `/providers/:id` | Profil public d'un prestataire |
| GET | `/requests`, `/requests/:id` | Demandes des clients |
| GET | `/lang/fr`, `/lang/en` | Changement de langue |
| GET | `/healthz` | Supervision |

### Comptes
| Méthode | Route | Rôle |
|---|---|---|
| GET/POST | `/register`, `/login` ; POST `/logout` | Inscription / connexion par téléphone |
| GET/POST | `/verify-phone` | Code SMS (si `PHONE_VERIFICATION=on`) |
| GET/POST | `/forgot`, POST `/reset` | Mot de passe oublié par code SMS |
| GET | `/account` | Tableau de bord (annonces, paiements, demandes) |
| GET/POST | `/account/edit`, POST `/account/password` | Profil |
| GET/POST | `/account/photo` | Envoi de photo + détection de visage |
| POST | `/account/photo/review` | Demande de validation manuelle |

### Annonces, demandes, messages, paiements
| Méthode | Route | Rôle |
|---|---|---|
| GET/POST | `/listings/new`, `/listings` | Création (prestataire avec photo validée) |
| GET/POST | `/listings/:id/edit` ; POST `/publish`, `/deactivate`, `/delete`, `/contact` | Gestion d'annonce |
| GET/POST | `/listings/:id/pay` | Choix de l'opérateur et lancement du paiement |
| GET | `/payments/:id`, `/api/payments/:id/status` | Suivi du paiement (actualisation automatique) |
| GET/POST | `/webhooks/campay` | Notification CamPay |
| GET/POST | `/requests/new`, `/requests` ; POST `/requests/:id/respond`, `/close` | Demandes des clients |
| GET | `/messages`, `/messages/:id` ; POST `/messages/:id` ; GET `/api/messages/:id?after=` | Messagerie |
| POST | `/report` | Signalement |

### Administration (`/admin`, rôle admin uniquement)
Tableau de bord, `/admin/settings` (tarifs, gratuité, catégories), `/admin/photos` (validation manuelle), `/admin/users` (suspension, retrait de photo), `/admin/listings` (suspension d'annonces et de demandes), `/admin/payments` (revérification), `/admin/reports`.

## Flux de publication et de paiement

```
Prestataire crée l'annonce
        │
        ▼
Gratuité de lancement active ?  (activée, avant la date de fin, quota global non atteint,
        │                         quota par prestataire non atteint ; compteur verrouillé en base)
   oui ─┴─► annonce « active » gratuitement (is_free_promo = true)
   non
        ▼
Tarif (catégorie ou global) = 0 ? ── oui ──► annonce « active »
        │ non
        ▼
annonce « pending_payment » → page de paiement
        │  choix MTN / Orange + numéro (contrôle préfixe ↔ opérateur)
        ▼
POST CamPay /api/collect/  → paiement « pending » + code USSD affiché
        │
        ├─► la page interroge /api/payments/:id/status toutes les 3–6 s
        │        └─► le serveur interroge CamPay GET /api/transaction/{ref}/
        └─► CamPay appelle /webhooks/campay
                 └─► le serveur interroge CamPay (on ne croit jamais la notification seule)
        ▼
SUCCESSFUL (montant ≥ attendu) → transaction : paiement « successful » + annonce « active » pour N jours
FAILED ou > 20 min sans réponse → paiement « failed », bouton « Réessayer »
```

## Flux de modération des photos

```
Envoi de la photo (JPG/PNG/WebP, 8 Mo max., 200×200 px min.)
   ▼
Contrôles : luminosité, netteté (variance du laplacien)
   ▼
Détection de visages (score ≥ 0,5)
   ├─ 0 visage ......................... refus « aucun visage »
   ├─ 2 visages ou plus ................ refus « plusieurs visages »
   ├─ visage < 12 % de la largeur ...... refus « visage trop petit »
   └─ exactement 1 visage .............. ACCEPTÉE → recadrée 480×480, WebP, EXIF supprimés, publique
   ▼ (refus)
L'image refusée est gardée dans uploads/pending (NON publique)
Après 2 refus (PHOTO_MAX_FAILURES) ou si le service est indisponible :
   bouton « Demander une vérification manuelle »
   ▼
Admin → /admin/photos → Approuver (devient la photo publique) ou Refuser
```

Sans photo validée, un prestataire ne peut pas publier d'annonce et un client ne peut pas publier de demande. Les deux peuvent déjà naviguer et écrire des messages.

## Sécurité

- Mots de passe hachés avec **bcrypt** (coût 12). Session régénérée à la connexion.
- **CSRF** : jeton par session sur tous les formulaires (et après multer pour les envois de fichiers).
- **CSP stricte** (aucun script ni style en ligne), `X-Frame-Options`, HSTS (Helmet).
- Cookies `HttpOnly`, `SameSite=Lax`, `Secure` en production.
- **Limitation de débit** : connexion/inscription, codes SMS, envois de photos, paiements, messages.
- Requêtes SQL toujours paramétrées. Tri et pagination issus de listes blanches.
- Échappement HTML automatique (EJS `<%= %>`), vérifié par les tests.
- Photos ré-encodées : suppression des métadonnées (GPS) et de tout contenu caché.
- Photos en attente servies uniquement à l'admin.
- Paiement : statut toujours confirmé auprès de l'API CamPay, montant vérifié, finalisation idempotente.
- Suspension d'un utilisateur : ses annonces sont suspendues et ses sessions supprimées.
