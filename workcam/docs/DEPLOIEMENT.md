# Mise en ligne pas à pas

Objectif : un seul serveur (VPS) qui fait tourner le site, la base de données et le HTTPS automatique, pour moins de 10 €/mois.

## Budget mensuel

| Poste | Coût indicatif | Remarque |
|---|---|---|
| VPS 2 vCPU / 4 Go RAM | **4–6 €/mois** | Hetzner (CX22 ou équivalent) ou Contabo (Cloud VPS) |
| Nom de domaine `.cam` ou `.com` | **≈ 1–2 €/mois** (10–25 €/an) | Namecheap, Porkbun, OVH… Vérifiez la disponibilité de `work.cam` : les noms courts peuvent être « premium » (bien plus chers) |
| Détection de visage | **0 €** | Modèle local inclus |
| HTTPS | **0 €** | Let's Encrypt via Caddy |
| SMS (facultatif) | variable | Seulement si vous activez la vérification par SMS |
| Paiement | commission par transaction | Prélevée par l'agrégateur, pas d'abonnement |
| **Total** | **≈ 6–8 €/mois** | Tarifs des fournisseurs à vérifier au moment de l'achat |

Pourquoi l'Europe plutôt qu'un hébergeur camerounais ? La latence Europe–Cameroun (≈ 100–150 ms) suffit largement pour ce site. Les VPS européens sont moins chers, plus fiables et se paient facilement par carte. Un hébergeur local reste envisageable plus tard si vos utilisateurs le préfèrent.

Évitez les offres gratuites (Vercel Hobby, etc.) : elles interdisent souvent l'usage commercial et ne conviennent pas à une base PostgreSQL ni au modèle de détection de visage.

## 1. Acheter le domaine

Chez un registrar (Namecheap, Porkbun, OVH…), achetez le domaine. Laissez la zone DNS vide pour l'instant.

## 2. Louer le VPS

- Système : **Ubuntu 24.04 LTS**.
- Taille minimale : 2 vCPU, **4 Go de RAM** (le modèle de visage + PostgreSQL + Node tiennent dans ≈ 1 Go, la marge sert aux pics).
- Ajoutez votre **clé SSH** à la création (plus sûr qu'un mot de passe).
- Notez l'**adresse IP** du serveur.

## 3. Pointer le domaine vers le serveur

Dans la zone DNS du registrar, créez :

| Type | Nom | Valeur |
|---|---|---|
| A | `@` | IP du VPS |
| A | `www` | IP du VPS |

La propagation prend de quelques minutes à quelques heures.

## 4. Préparer le serveur

```bash
ssh root@IP_DU_VPS
```

```bash
apt update && apt upgrade -y
```

```bash
curl -fsSL https://get.docker.com | sh
```

```bash
ufw allow OpenSSH && ufw allow 80 && ufw allow 443 && ufw --force enable
```

## 5. Installer Work.cam

```bash
mkdir -p /opt && cd /opt && git clone https://github.com/VOTRE-COMPTE/VOTRE-DEPOT.git workcam-src
```

```bash
ln -s /opt/workcam-src/workcam /opt/workcam && cd /opt/workcam
```

Pour un dépôt privé, ajoutez d'abord une *deploy key* GitHub au serveur, ou copiez le dossier avec `scp -r`.

Créez la configuration :

```bash
cp .env.example .env && nano .env
```

À remplir :
- `BASE_URL=https://votre-domaine` et `DOMAIN=votre-domaine`
- `SESSION_SECRET` : générez-le avec `openssl rand -hex 48`
- `POSTGRES_PASSWORD` : un mot de passe long, reporté dans `DATABASE_URL=postgres://workcam:CE_MOT_DE_PASSE@db:5432/workcam`
- `PAYMENT_GATEWAY=campay` et les identifiants CamPay (voir [PAIEMENT.md](PAIEMENT.md))
- `SUPPORT_PHONE`, `SUPPORT_EMAIL`

Lancez :

```bash
docker compose up -d --build
```

```bash
docker compose logs -f app
```

Vous devez voir « Work.cam en ligne » puis « modèle local chargé ». Caddy obtient le certificat HTTPS tout seul dès que le DNS pointe sur le serveur.

Créez votre compte administrateur :

```bash
docker compose exec app node scripts/create-admin.js 6XXXXXXXX "MotDePasseTrèsSolide" "Votre Nom"
```

Ouvrez `https://votre-domaine`, connectez-vous, puis allez dans **Administration → Tarifs & promotion** pour fixer les tarifs et la gratuité de lancement.

## 6. Sauvegardes (indispensable)

```bash
crontab -e
```

Ajoutez la ligne :

```
0 3 * * * cd /opt/workcam && ./deploy/backup.sh >> /var/log/workcam-backup.log 2>&1
```

Le script garde 14 jours de sauvegardes (base + photos) dans `/opt/workcam-backups`. **Copiez-les aussi hors du serveur** (votre ordinateur, ou un stockage objet à quelques centimes par mois). Une sauvegarde qui reste sur le même serveur ne protège pas d'une panne du serveur.

Restauration de la base :

```bash
docker compose exec -T db pg_restore -U workcam -d workcam --clean < /opt/workcam-backups/db-AAAAMMJJ-HHMM.dump
```

## 7. Mettre à jour le site

```bash
cd /opt/workcam-src && git pull && cd /opt/workcam && docker compose up -d --build
```

Le schéma de base de données se met à jour automatiquement au démarrage (scripts idempotents).

## 8. Surveillance

- `https://votre-domaine/healthz` répond `{"ok":true}` quand le site et la base fonctionnent. Branchez-le sur un service de surveillance gratuit (UptimeRobot, etc.) pour être alerté par e-mail.
- Logs : `docker compose logs --tail=200 app`.

## Sans Docker (alternative)

Installez Node.js 22, PostgreSQL 16 et Caddy directement sur le serveur, puis lancez `npm ci --omit=dev && npm start` sous un gestionnaire de service (systemd ou pm2). Gardez la configuration Caddy de `deploy/Caddyfile` en remplaçant `app:3000` par `localhost:3000`.

## Liste de contrôle avant l'ouverture

- [ ] `NODE_ENV=production`, `SESSION_SECRET` aléatoire, mots de passe forts
- [ ] Paiement testé en démo CamPay puis **un vrai paiement** en production avec votre numéro
- [ ] URL de webhook déclarée chez CamPay
- [ ] Données de démonstration absentes (`npm run seed:demo -- --clean` si vous en aviez mis)
- [ ] Conditions d'utilisation et politique de confidentialité relues par un juriste (le Cameroun encadre la protection des données personnelles : vérifiez les obligations actuelles)
- [ ] Sauvegardes automatiques en place **et** testées par une restauration
- [ ] Numéro et e-mail de support renseignés
