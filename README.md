# Fiche Technique Auto

Application web destinée à construire automatiquement un dossier de fiches techniques à partir d'un descriptif.

## Objectif

1. Importer un descriptif PDF, DOCX ou TXT.
2. Détecter l'ordre des titres et des produits.
3. Rechercher automatiquement les fiches techniques correspondantes dans une bibliothèque.
4. Demander une validation uniquement lorsqu'une correspondance est incertaine.
5. Générer un PDF final composé de pages de titres et des PDF fabricants originaux.

## Règle principale

Les fiches techniques fabricants ne sont jamais recréées, retouchées, recadrées ou modifiées. Le PDF original est conservé et sera inséré tel quel dans le dossier final.

## Bibliothèque

La V1 est prévue pour utiliser :
- Supabase PostgreSQL pour les métadonnées ;
- Supabase Storage pour les PDF originaux ;
- Streamlit pour l'interface web.

L'ajout normal d'une fiche est automatique : l'utilisateur dépose un ou plusieurs PDF, le système extrait le texte, propose le nom du produit, la marque, la référence et des alias, puis l'utilisateur valide ou corrige si nécessaire.

## État actuel

- [x] Structure du projet
- [x] Interface Streamlit
- [x] Lecture PDF / DOCX / TXT
- [x] Import de plusieurs fiches PDF
- [x] Première détection automatique des métadonnées
- [x] Recherche approximative par nom et alias
- [x] Schéma Supabase
- [ ] Connexion au projet Supabase réel
- [ ] Analyse complète titres / produits du descriptif
- [ ] Écran de validation de l'ordre
- [ ] Génération des pages de titre selon le modèle fourni
- [ ] Fusion PDF finale
- [ ] Déploiement Streamlit public
