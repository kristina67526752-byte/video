# Vérification des photos de profil

## Ce qui est vérifié

Code : `src/services/faceDetection.js`.

1. **Format** : JPG, PNG ou WebP, 8 Mo maximum, au moins 200×200 pixels.
2. **Luminosité** moyenne ≥ 25/255 (sinon « trop sombre »).
3. **Netteté** : écart-type du laplacien ≥ 4. Rejette les images floues et les aplats (logos simples, fonds unis).
4. **Détection de visages** avec le modèle SSD MobileNet v1 (confiance ≥ 0,5) :
   - 0 visage → refus « aucun visage » (paysages, objets, logos…)
   - 2 visages ou plus → refus « plusieurs visages » (photos de groupe)
   - visage < 12 % de la largeur → refus « visage trop petit »
   - exactement 1 visage → **acceptée**

Mesuré sur le serveur de test : 0,3 à 0,7 seconde par photo, modèle chargé une fois au démarrage.

## Pourquoi un modèle local par défaut

| Option | Coût | Avantages | Inconvénients |
|---|---|---|---|
| **Local** (défaut, `FACE_PROVIDER=local`) | 0 € | Aucune photo envoyée à un tiers, pas de clé, pas de quota | Utilise ≈ 300 Mo de RAM, un peu moins précis sur les cas difficiles |
| Google Cloud Vision (`FACE_PROVIDER=google`) | Gratuit jusqu'à 1 000 images/mois, puis environ 1,50 $ les 1 000 (à vérifier) | Très fiable, détecte aussi les dessins | Clé API, carte bancaire, photos envoyées à Google |
| Azure Face | Accès à la détection soumis à conditions | — | Procédure d'accès plus lourde |

Pour un démarrage à petit budget, le modèle local suffit pour la règle « un seul vrai visage ». Si les faux positifs deviennent gênants, passez à Google Vision en changeant seulement `FACE_PROVIDER` et `GOOGLE_VISION_API_KEY`.

## Limites connues

Aucune détection automatique n'est parfaite :
- **Photo de célébrité ou trouvée sur Internet** : un portrait de star contient bien un seul visage, il sera accepté. Seule l'identification ou la comparaison avec une pièce d'identité l'empêcherait (hors périmètre et sensible juridiquement). D'où le **signalement** et la **suppression de photo** par l'admin.
- **Dessins très réalistes, statues** : parfois acceptés.
- **Faux refus** : visage de profil, lunettes de soleil, forte ombre, éclairage très faible. C'est l'objet de la validation manuelle.

## Validation manuelle (secours)

- Après **2 refus** (réglable via `PHOTO_MAX_FAILURES`), ou immédiatement si le service de détection est indisponible, l'utilisateur voit **« Demander une vérification manuelle »**, avec un champ de message facultatif.
- La photo refusée est conservée dans `uploads/pending/`, **jamais servie publiquement** : seule la route admin `/admin/photos/:id/image` y accède.
- L'admin approuve (la photo devient publique et le profil est validé) ou refuse (avec un motif). Pendant l'attente, l'utilisateur peut essayer d'autres photos ; une photo acceptée automatiquement annule la demande en attente.
- Objectif conseillé : traiter les demandes **sous 24 h**. Le menu admin affiche un compteur des demandes en attente.

## Réglages

Les seuils sont des constantes en haut de `faceDetection.js` (`MIN_FACE_RATIO`, `MIN_SHARPNESS`, `MIN_BRIGHTNESS`, `MIN_SCORE`). Après le lancement, regardez dans `/admin/photos` les raisons de rejet des demandes manuelles que vous approuvez. Si une raison revient souvent (par exemple « trop sombre » pour des photos correctes), assouplissez le seuil correspondant.

## Vie privée

Les photos sont ré-encodées en WebP 480×480 : les métadonnées EXIF (dont la position GPS) sont supprimées. Aucune empreinte faciale n'est calculée ni stockée : le système détecte la présence d'un visage, il n'identifie personne.
