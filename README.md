# Exam Prep — Documentation

Application d'entraînement aux certifications (CDMP, AI-900, DP-300, AZ-104, DP-700).
Chaque examen est autonome : banque de questions SQLite, historique des sessions,
apprentissage adaptatif, traduction multilingue.

---

## Table des matières

1. [Arborescence](#1-arborescence)
2. [Modes de fonctionnement](#2-modes-de-fonctionnement)
3. [Démarrage rapide](#3-démarrage-rapide)
4. [Structure des bases de données SQLite](#4-structure-des-bases-de-données-sqlite)
5. [Format des fichiers de configuration](#5-format-des-fichiers-de-configuration)
6. [Scripts utilitaires](#6-scripts-utilitaires)
7. [Ajouter un examen](#7-ajouter-un-examen)
8. [Export et import de données](#8-export-et-import-de-données)
9. [Architecture de chargement](#9-architecture-de-chargement)

---

## 1. Arborescence

```
./
├── cdmp_exam_dmbok2.html          Application (fichier unique)
│
├── bin/
│   ├── serve.py                   Serveur HTTP + proxy Anthropic API (traduction)
│   └── sqlite2js.py               Convertisseur SQLite/JSON → .js (mode file://)
│
├── exams/                         Définitions des examens
│   ├── index.json                 Liste des identifiants d'examens disponibles
│   ├── index.js                   Même contenu, chargeable sans serveur (file://)
│   ├── cdmp.json                  Paramètres de l'examen CDMP
│   ├── cdmp.js                    Idem, format .js
│   ├── ai900.json / ai900.js
│   ├── dp300.json / dp300.js
│   ├── az104.json / az104.js
│   └── dp700.json / dp700.js
│
├── sql/                           Scripts SQL de création des structures
│   ├── 00_full_schema.sql             Schéma complet (questions + historique + traductions)
│   ├── 01_questions.sql               Banque de questions seule
│   ├── 02_history.sql                 Tables d'historique (sessions, réponses)
│   ├── 03_translations.sql            Traductions multilingues
│   └── 04_history_export.sql          Schéma du fichier d'export historique
│
└── data/
    ├── content/                   Banques de questions (lecture seule)
    │   ├── cdmp.sqlite            600 questions CDMP/DMBOK2
    │   ├── cdmp.sqlite.js         Idem encodé en base64 (mode file://)
    │   ├── ai900.sqlite           36 questions AI-900
    │   ├── ai900.sqlite.js
    │   ├── dp300.sqlite           546 questions DP-300
    │   ├── dp300.sqlite.js
    │   ├── az104.sqlite           123 questions AZ-104
    │   ├── az104.sqlite.js
    │   ├── dp700.sqlite           229 questions DP-700
    │   └── dp700.sqlite.js
    └── results/                   Historiques initiaux (optionnel)
        └── <id>_history.sqlite    Chargé et fusionné au premier démarrage
```

---

## 2. Modes de fonctionnement

L'application supporte deux modes sans modification du code :

| Mode | Prérequis | Cascade de chargement |
|------|-----------|----------------------|
| **Double-clic** (`file://`) | Fichiers `.js` présents | `.js` via `<script>` |
| **Serveur HTTP** | `python3 bin/serve.py` | `.js` puis `fetch` sur `.sqlite` |
| **Import manuel** | Aucun | `<input type=file>` proposé si les autres échouent |

Les fichiers `.js` sont générés par `bin/sqlite2js.py` et embarquent les données
en base64. Les balises `<script src>` ne sont pas soumises à la politique CORS,
contrairement à `fetch()`.

---

## 3. Démarrage rapide

### Mode file:// (sans serveur)

```bash
# Générer les fichiers .js (une seule fois, puis après chaque modification)
python3 bin/sqlite2js.py

# Ouvrir le HTML directement dans le navigateur
open cdmp_exam_dmbok2.html          # macOS
xdg-open cdmp_exam_dmbok2.html      # Linux
start cdmp_exam_dmbok2.html         # Windows
```

### Mode HTTP (avec serveur)

```bash
python3 bin/serve.py                 # localhost:8080
python3 bin/serve.py --port 3000     # port personnalisé
python3 bin/serve.py --host 0.0.0.0  # exposer sur le réseau

# Puis ouvrir : http://localhost:8080/cdmp_exam_dmbok2.html
```

Le `serve.py` sert également de proxy pour l'API Anthropic (traduction des
questions en français via Claude Haiku, contournement CORS).

---

## 4. Structure des bases de données SQLite

### 4.1 Base de contenu — `data/content/<id>.sqlite`

Contient les questions et, après le premier examen passé, l'historique complet
(questions + résultats fusionnés par `ensureResultsTables`).

#### Table `questions`

Schéma minimal (CDMP, AI-900) — 4 options :

| Colonne | Type | Contrainte | Description |
|---------|------|-----------|-------------|
| `id` | INTEGER | PK AUTOINCREMENT | Identifiant unique de la question |
| `domain` | TEXT | NOT NULL | Domaine / thème (ex. « Data Governance ») |
| `question` | TEXT | NOT NULL | Texte de la question |
| `opt_a` | TEXT | NOT NULL | Option A |
| `opt_b` | TEXT | NOT NULL | Option B |
| `opt_c` | TEXT | NOT NULL | Option C |
| `opt_d` | TEXT | NOT NULL | Option D |
| `correct_idx` | TEXT | NOT NULL | Index(es) de la/des bonne(s) réponse(s) (voir note) |
| `explanation` | TEXT | NOT NULL | Explication affichée après réponse |
| `is_complex` | INTEGER | NOT NULL DEFAULT 0 | Réservé (complexité, non utilisé actuellement) |

Schéma étendu (DP-300, AZ-104, DP-700, examens personnalisés) — 6 options + multi-select :

| Colonne | Type | Contrainte | Description |
|---------|------|-----------|-------------|
| `opt_e` | TEXT | DEFAULT '' | Option E (vide si inutilisée) |
| `opt_f` | TEXT | DEFAULT '' | Option F (vide si inutilisée) |
| `is_multi` | INTEGER | NOT NULL DEFAULT 0 | 1 = question à choix multiples |
| `select_count` | INTEGER | NOT NULL DEFAULT 1 | Nombre de réponses attendues |

> **Note `correct_idx`** : pour les questions à choix unique, c'est l'index de
> l'option correcte (0, 1, 2…). Pour les questions multi-select, c'est une chaîne
> de la forme `"0,2"` listant les index corrects. La valeur est stockée sous forme
> de `TEXT` pour supporter les deux cas.
>
> En mémoire, le moteur ne stocke jamais l'index brut — il calcule un hash
> `SHA-1` de la valeur de l'option correcte (sel interne) pour éviter que
> l'inspect du DOM révèle la réponse.

**Index :** `uq_q UNIQUE ON (question)` — garantit l'absence de doublons.

#### Table `meta`

| Colonne | Type | Description |
|---------|------|-------------|
| `key` | TEXT PK | Clé (`version`, `question_count`) |
| `value` | TEXT | Valeur associée |

Entrées présentes :

| key | Exemple | Rôle |
|-----|---------|------|
| `version` | `"4"` | Version de la banque ; si la version en cache IDB est inférieure, la base est rechargée |
| `question_count` | `"546"` | Nombre de questions (pour l'affichage) |

#### Table `question_translations`

Créée à la demande lors de la première traduction (via Claude Haiku).

| Colonne | Type | Description |
|---------|------|-------------|
| `question_id` | INTEGER | Référence à `questions.id` |
| `lang` | TEXT | Code langue (`fr`, `es`…) |
| `question` | TEXT | Texte traduit |
| `opt_a`…`opt_f` | TEXT | Options traduites |
| `explanation` | TEXT | Explication traduite |

**Clé primaire composite :** `(question_id, lang)`.

---

### 4.2 Tables d'historique

Ces tables sont ajoutées dans la base de contenu par `ensureResultsTables()`
au premier chargement. Elles sont également présentes dans les fichiers exportés
`data/results/<id>_history.sqlite`.

#### Table `sessions`

Une ligne par examen passé.

| Colonne | Type | Contrainte | Description |
|---------|------|-----------|-------------|
| `id` | INTEGER | PK AUTOINCREMENT | Identifiant de session |
| `started_at` | TEXT | NOT NULL | Horodatage ISO 8601 de début — **clé métier pour la déduplication à l'import** |
| `completed_at` | TEXT | NOT NULL | Horodatage ISO 8601 de fin |
| `score` | INTEGER | NOT NULL | Nombre de bonnes réponses |
| `attempted` | INTEGER | NOT NULL | Nombre de questions répondues (hors skip) |
| `cx_correct` | INTEGER | DEFAULT 0 | Bonnes réponses aux questions complexes |
| `cx_total` | INTEGER | DEFAULT 0 | Total questions complexes posées |
| `duration_sec` | INTEGER | DEFAULT 0 | Durée nette d'examen en secondes (hors pause) |
| `quiz_id` | TEXT | DEFAULT '' | Identifiant de l'examen (`cdmp`, `dp300`…) |
| `quiz_title` | TEXT | DEFAULT '' | Titre affiché (peut être personnalisé via config screen) |
| `total_questions` | INTEGER | DEFAULT 0 | Nombre total de questions du tirage |

#### Table `domain_scores`

Scores détaillés par domaine pour chaque session.

| Colonne | Type | Contrainte | Description |
|---------|------|-----------|-------------|
| `id` | INTEGER | PK AUTOINCREMENT | — |
| `session_id` | INTEGER | NOT NULL FK → sessions | Session parente |
| `domain` | TEXT | NOT NULL | Nom du domaine |
| `correct` | INTEGER | NOT NULL | Bonnes réponses dans ce domaine |
| `total` | INTEGER | NOT NULL | Questions posées dans ce domaine |

**Index :** `idx_ds_sid ON (session_id)`.

#### Table `session_answers`

Réponse fournie pour chaque question d'un examen.

| Colonne | Type | Contrainte | Description |
|---------|------|-----------|-------------|
| `id` | INTEGER | PK AUTOINCREMENT | — |
| `session_id` | INTEGER | NOT NULL FK → sessions | Session parente |
| `question_id` | INTEGER | DEFAULT NULL | Référence à `questions.id` — utilisé par le mode adaptatif pour identifier les questions maîtrisées |
| `question_idx` | INTEGER | NOT NULL DEFAULT 0 | Position (0-based) dans le tirage de cette session |
| `question` | TEXT | NOT NULL | Texte de la question au moment de l'examen (langue active) |
| `domain` | TEXT | NOT NULL | Domaine de la question |
| `answer_given` | TEXT | DEFAULT NULL | Texte de l'option choisie ; `NULL` si la question a été passée ; séparateur ` \| ` pour les multi-select |
| `correct_answer` | TEXT | NOT NULL | Texte de la/des bonne(s) réponse(s) ; séparateur ` \| ` pour les multi-select |
| `is_correct` | INTEGER | NOT NULL DEFAULT 0 | `1` = bonne réponse, `0` = mauvaise ou passée |
| `explanation` | TEXT | NOT NULL | Explication complète |

**Index :** `idx_ans_sid ON (session_id)`.

> **Mode adaptatif** : lors de la préparation d'un examen avec le mode adaptatif
> activé, l'application interroge les 3 dernières sessions et identifie les
> `question_id` répondus correctement ≥ 2 fois. Ces questions sont placées dans
> un pool « maîtrisées » (15 % du tirage). Les autres constituent le pool « à
> réviser » (85 %).

---

### 4.3 Base d'historique exportée — `data/results/<id>_history.sqlite`

Fichier autonome produit par le bouton **Sauvegarder l'historique**.
Il contient uniquement les données de résultats, **sans les questions**.

Tables présentes : `sessions`, `domain_scores`, `session_answers`, `meta`.

Table `meta` spécifique :

| key | Valeur exemple | Description |
|-----|---------------|-------------|
| `version` | `"1"` | Version du format d'export |
| `app` | `"ExamPrep"` | Identification de l'application source |

**Import / fusion :** lors du chargement d'un fichier historique (bouton
**Restaurer un historique** ou au démarrage si le fichier existe dans
`data/results/`), chaque session est insérée avec déduplication sur `started_at` :
si la date existe déjà, elle est reculée d'une seconde jusqu'à trouver un slot
libre (jusqu'à 300 tentatives).

---

## 5. Format des fichiers de configuration

### `exams/index.json`

```json
{
  "exams": ["cdmp", "ai900", "dp300", "az104", "dp700"]
}
```

Ordre d'affichage dans le picker. Ajouter un identifiant ici et créer le fichier
de config correspondant suffit à enregistrer un nouvel examen.

### `exams/<id>.json`

```json
{
  "id":            "dp300",
  "title":         "DP-300",
  "subtitle":      "Azure Database Administrator Associate",
  "description":   "HTML affiché sur la carte du picker (balises autorisées)",
  "version":       4,
  "perExam":       55,
  "timeMin":       100,
  "passThreshold": 70,
  "refLabel":      "Microsoft Azure DP-300",
  "cssClass":      "dp300",
  "contentFile":   "dp300.sqlite",
  "resultsFile":   "dp300_history.sqlite"
}
```

| Champ | Type | Description |
|-------|------|-------------|
| `id` | string | Identifiant unique, sans espaces |
| `title` | string | Titre court affiché sur la carte et dans l'interface |
| `subtitle` | string | Sous-titre affiché sous le titre |
| `description` | string | Description HTML sur la carte du picker |
| `version` | integer | Version de la banque ; incrémenter force le rechargement du cache IDB |
| `perExam` | integer | Nombre de questions par défaut dans l'écran de configuration |
| `timeMin` | integer | Durée par défaut en minutes |
| `passThreshold` | integer | Score de réussite en pourcentage |
| `refLabel` | string | Libellé de la référence (affiché dans l'interface) |
| `cssClass` | string | Classe CSS appliquée à la carte (pour la couleur d'accentuation) |
| `contentFile` | string | Nom du fichier SQLite dans `data/content/` |
| `resultsFile` | string | Nom du fichier d'historique dans `data/results/` |

---

## 6. Scripts utilitaires

### `bin/serve.py`

Serveur HTTP statique + proxy de traduction.

```
python3 bin/serve.py [--port PORT] [--host HOST]
```

| Option | Défaut | Description |
|--------|--------|-------------|
| `--port` | `8080` | Port d'écoute |
| `--host` | `127.0.0.1` | Interface réseau (`0.0.0.0` pour exposer sur le LAN) |

Endpoints :

| Méthode | Chemin | Description |
|---------|--------|-------------|
| GET | `/*` | Fichiers statiques servis depuis la racine du projet |
| POST | `/api/translate` | Proxy vers `api.anthropic.com/v1/messages` (CORS) |

La clé API Anthropic est passée par le navigateur dans l'en-tête `X-Api-Key`
et retransmise au proxy sans être stockée côté serveur.

### `bin/sqlite2js.py`

Convertit les fichiers de données en modules `.js` chargeables sans serveur.

```
python3 bin/sqlite2js.py [--watch] [--clean]
```

| Option | Description |
|--------|-------------|
| _(aucune)_ | Convertit tous les fichiers une fois |
| `--watch` | Surveille les modifications et reconvertit automatiquement |
| `--clean` | Supprime tous les fichiers `.js` générés |

Fichiers générés :

| Source | Destination | Variable globale |
|--------|-------------|-----------------|
| `exams/index.json` | `exams/index.js` | `window.__EXAM_INDEX` |
| `exams/<id>.json` | `exams/<id>.js` | `window.__EXAM_CONFIGS['<id>']` |
| `data/content/*.sqlite` | `data/content/*.sqlite.js` | `window.__EXAM_CONTENT['<file>']` |
| `data/results/*.sqlite` | `data/results/*.sqlite.js` | `window.__EXAM_RESULTS['<file>']` |

Les données SQLite sont encodées en base64 dans le `.js`. À relancer après toute
modification d'un `.sqlite` ou `.json`.

---

## 7. Scripts SQL

Les scripts dans `./sql/` permettent de créer les structures SQLite manuellement
ou de les documenter pour des outils externes (DB Browser for SQLite, DBeaver…).

| Fichier | Usage |
|---------|-------|
| `00_full_schema.sql` | Schéma complet en une passe (questions + historique + traductions) |
| `01_questions.sql` | Banque de questions seule, avec exemples d'insertion |
| `02_history.sql` | Tables de sessions, scores par domaine, réponses par question |
| `03_translations.sql` | Traductions multilingues avec requêtes de diagnostic |
| `04_history_export.sql` | Format du fichier exporté via "Sauvegarder l'historique" |

Création d'une nouvelle base à partir des scripts :

```bash
# Base complète
sqlite3 data/content/monexamen.sqlite < sql/00_full_schema.sql

# Ou étape par étape
sqlite3 data/content/monexamen.sqlite < sql/01_questions.sql
sqlite3 data/content/monexamen.sqlite < sql/02_history.sql
sqlite3 data/content/monexamen.sqlite < sql/03_translations.sql

# Base d'historique autonome
sqlite3 data/results/monexamen_history.sqlite < sql/04_history_export.sql
```

## 8. Ajouter un examen

### Examen depuis un fichier SQLite existant

1. Déposer le fichier de questions dans `data/content/monexamen.sqlite`
   (schéma : voir §4.1)
2. Créer `exams/monexamen.json` avec les paramètres
3. Ajouter `"monexamen"` à la liste dans `exams/index.json`
4. Régénérer les `.js` : `python3 bin/sqlite2js.py`

### Examen vide depuis l'interface

Dans le picker, cliquer sur **➕ Ajouter un examen**. L'interface propose de
renseigner le titre, la durée, le seuil de réussite et d'importer optionnellement
un fichier `.sqlite`. Sans fichier, une base vide est créée avec le schéma complet.
Les métadonnées sont sauvegardées dans `localStorage`, la base dans IndexedDB.

### Schéma SQLite minimal pour une banque de questions importée

```sql
CREATE TABLE questions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    domain       TEXT    NOT NULL DEFAULT 'General',
    question     TEXT    NOT NULL,
    opt_a        TEXT    NOT NULL DEFAULT '',
    opt_b        TEXT    NOT NULL DEFAULT '',
    opt_c        TEXT    NOT NULL DEFAULT '',
    opt_d        TEXT    NOT NULL DEFAULT '',
    opt_e        TEXT             DEFAULT '',   -- optionnel
    opt_f        TEXT             DEFAULT '',   -- optionnel
    correct_idx  TEXT    NOT NULL DEFAULT '0',  -- '0'..'5' ou '0,2' pour multi
    explanation  TEXT    NOT NULL DEFAULT '',
    is_complex   INTEGER NOT NULL DEFAULT 0,
    is_multi     INTEGER NOT NULL DEFAULT 0,    -- 1 = choix multiples
    select_count INTEGER NOT NULL DEFAULT 1     -- nb de réponses attendues
);

CREATE TABLE meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

INSERT INTO meta VALUES ('version', '1');
INSERT INTO meta VALUES ('question_count', '0'); -- mis à jour automatiquement
```

---

## 9. Export et import de données

### Depuis l'écran de démarrage (par examen)

| Bouton | Fichier produit | Contenu |
|--------|----------------|---------|
| 📥 Exporter la base | `<id>_YYYY-MM-DD.sqlite` | Questions + traductions + historique complet |
| 📤 Importer une base | — | Remplace la base active en IndexedDB |

### Depuis l'écran d'historique

| Bouton | Fichier produit | Contenu |
|--------|----------------|---------|
| 📥 Sauvegarder l'historique | `<id>_history_YYYY-MM-DD.sqlite` | Sessions + scores + réponses, **sans questions** |
| 📤 Restaurer un historique | — | Fusionne avec déduplication sur `started_at` |

Le fichier d'historique exporté est compatible avec le chargement automatique :
le déposer dans `data/results/<id>_history.sqlite` et régénérer les `.js` le
fera charger automatiquement au prochain premier démarrage de cet examen.

---

## 10. Architecture de chargement

```
Ouverture de la page
        │
        ▼
initSQLjs()          Charge sql.js (WebAssembly SQLite en mémoire)
        │
        ▼
loadExamDefinitions()
  ┌─────────────────────────────────────┐
  │ 1. loadScript(exams/index.js)       │  file:// ✓
  │    → window.__EXAM_INDEX            │
  │ 2. fetch(exams/index.json)          │  HTTP uniquement
  │ 3. Pour chaque id :                 │
  │    a. window.__EXAM_CONFIGS[id]     │  déjà chargé
  │    b. loadScript(exams/<id>.js)     │  file:// ✓
  │    c. fetch(exams/<id>.json)        │  HTTP uniquement
  └─────────────────────────────────────┘
        │
        ▼
_renderPicker()      Affiche les cartes des examens
        │
  (clic sur une carte)
        │
        ▼
loadQuiz(quiz)
  ┌─────────────────────────────────────────────────────┐
  │ idbGet(quiz.dbKey)  → IndexedDB (cache navigateur)  │
  │   version OK ?  ──oui──▶ showLangScreen()           │
  │       │ non                                         │
  │       ▼                                             │
  │ _loadDataAsset(contentFile)                         │
  │   1. window.__EXAM_CONTENT[file]   (déjà en mém.)   │
  │   2. loadScript(content/<file>.js) (file:// ✓)      │
  │   3. fetch(data/content/<file>)    (HTTP)            │
  │   4. _promptManualImport()         (sélection fichier)│
  │       │                                             │
  │       ▼                                             │
  │ _loadDataAsset(resultsFile)  [si existe]            │
  │   → même cascade                                    │
  │   → _mergeResultsInto() si trouvé                   │
  │       │                                             │
  │       ▼                                             │
  │ ensureResultsTables()  + persistDB(IDB)             │
  │ location.reload() [1ère fois pour compteurs]        │
  └─────────────────────────────────────────────────────┘
        │
        ▼
showLangScreen() ──▶ showConfigScreen() ──▶ startExam()
```

### Cache IndexedDB

Chaque base est mise en cache sous la clé `<id>_db`. L'application vérifie
le champ `meta.version` : si la version en cache est ≥ à `version` dans le
fichier de configuration, la base locale est réutilisée sans re-téléchargement.
Pour forcer un rechargement (mise à jour des questions), incrémenter `version`
dans le fichier `.json` et régénérer le `.js`.
