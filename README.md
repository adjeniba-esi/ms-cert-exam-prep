# Exam Prep — Documentation

Application d'entraînement aux certifications (CDMP, AI-900, DP-300, AZ-104, DP-700).
Chaque examen est autonome : banque de questions SQLite, historique des sessions,
apprentissage adaptatif, traduction multilingue, génération de QCM depuis YouTube.

---

## TL;DR

Application web d'entraînement aux certifications (CDMP, AI-900, DP-300, AZ-104, DP-700).
Fichier HTML unique (`Exam-Prep.html`) + banques de questions SQLite chargées directement
dans le navigateur via sql.js (WebAssembly). Aucune dépendance extérieure, aucun build.

| Mode | Fonctionnalités | Quand l'utiliser |
|------|-----------------|------------------|
| **file://** | Questions, historique, adaptatif | Utilisation hors-ligne, pas de réseau |
| **Serveur Python** | + Traduction Claude, YouTube, Ollama | Développement local |
| **Docker** | idem serveur Python | Test en container isolé |
| **Kubernetes** | idem + HTTPS, domaine public | Production |

### Mode 1 — Double-clic (`file://`)

```bash
python3 bin/sqlite2js.py   # génère les .js (une fois, puis après chaque .sqlite/.json modifié)
xdg-open Exam-Prep.html    # Linux  |  open Exam-Prep.html (macOS)  |  start Exam-Prep.html (Windows)
```

### Mode 2 — Serveur Python HTTP

```bash
pip install yt-dlp                     # optionnel, pour la génération depuis YouTube
python3 bin/serve.py                   # démarre sur http://localhost:8080
# Ouvrir : http://localhost:8080/Exam-Prep.html
```

Options utiles : `--port 3000`, `--host 0.0.0.0`, `--cors-origin https://mon-domaine.com`

### Mode 3 — Docker (test local en container)

```bash
docker build -t exam-prep-local .
docker run --rm -p 8080:8080 exam-prep-local
# Ouvrir : http://localhost:8080/Exam-Prep.html
```

### Mode 4 — Cluster Kubernetes (Kind)

```bash
cd deploy/
ansible-playbook deploy-k8s.yml -e ingress_domain=votre-domaine.com
# Disponible sur : https://votre-domaine.com/prep-exam/
```

---

## Table des matières

1. [Arborescence](#1-arborescence)
2. [Modes de fonctionnement](#2-modes-de-fonctionnement)
3. [Démarrage rapide](#3-démarrage-rapide)
4. [Structure des bases de données SQLite](#4-structure-des-bases-de-données-sqlite)
5. [Format des fichiers de configuration](#5-format-des-fichiers-de-configuration)
6. [Scripts utilitaires](#6-scripts-utilitaires)
7. [Pipeline YouTube → QCM](#7-pipeline-youtube--qcm)
8. [Ajouter un examen](#8-ajouter-un-examen)
9. [Export et import de données](#9-export-et-import-de-données)
10. [Architecture de chargement](#10-architecture-de-chargement)
11. [Déploiement Kubernetes](#11-déploiement-kubernetes)
12. [Interface d'administration](#12-interface-dadministration)

---

## 1. Arborescence

```
./
├── Exam-Prep.html                 Application (fichier unique, ~3500 lignes)
├── admin.html                     Interface d'administration (correction de questions)
├── Dockerfile                     Image de test local (python:3.12-slim + yt-dlp)
├── .dockerignore
├── .gitattributes                 Force LF sur tous les fichiers texte
│
├── bin/
│   ├── serve.py                   Serveur HTTP + proxy API + API admin
│   ├── sqlite2js.py               Convertisseur SQLite/JSON → .js (mode file://)
│   ├── get_playlist_transcripts.py  Télécharge les sous-titres d'une playlist YouTube
│   ├── transcript2questions.py    Génère des QCM depuis des transcripts via Claude
│   └── requirements.txt           Dépendances Python (yt-dlp)
│
├── js/
│   └── provider-meta.js           Helper _providerMeta() partagé (Anthropic/OpenAI/Mistral/Ollama)
│
├── exams/                         Définitions des examens
│   ├── index.json                 Liste des identifiants d'examens disponibles
│   ├── index.js                   Même contenu, chargeable sans serveur (file://)
│   ├── <id>.json                  Paramètres d'un examen (natif ou uploadé via admin)
│   └── <id>.js                    Idem, format .js
│
├── sql/                           Scripts SQL de création des structures
│   ├── 00_full_schema.sql
│   ├── 01_questions.sql
│   ├── 02_history.sql
│   ├── 03_translations.sql
│   └── 04_history_export.sql
│
└── data/
    ├── admin.js                   Credentials admin (sel + hash SHA-256, first_login)
    │                              ⚠ Bloqué en HTTP par nginx et serve.py (403)
    ├── content/                   Banques de questions
    │   ├── cdmp.sqlite            600 questions CDMP/DMBOK2
    │   ├── ai900.sqlite           36 questions AI-900
    │   ├── dp300.sqlite           546 questions DP-300
    │   ├── az104.sqlite           123 questions AZ-104
    │   ├── dp700.sqlite           229 questions DP-700
    │   ├── <id>.sqlite            Examens uploadés depuis l'admin
    │   └── *.sqlite.js            Variantes base64 (mode file://)
    └── results/                   Historiques initiaux (optionnel)
        └── <id>_history.sqlite
```

---

## 2. Modes de fonctionnement

| Mode | Prérequis | Traduction | Génération YouTube |
|------|-----------|------------|-------------------|
| **Double-clic** (`file://`) | Fichiers `.js` présents | ✗ | ✗ |
| **Serveur HTTP local** | `python3 bin/serve.py` | ✓ | ✓ |
| **Container Docker** | Docker | ✓ | ✓ |
| **Cluster Kubernetes** | Kind + ingress-nginx | ✓ | ✓ |

Les fichiers `.js` embarquent les données SQLite en base64 et sont chargés via
`<script src>` (non soumis au CORS). En mode `file://`, `fetch()` est bloqué.

---

## 3. Démarrage rapide

### Prérequis communs

```bash
# Python 3.9+ requis
python3 --version

# Installer les dépendances optionnelles (yt-dlp pour les transcripts YouTube)
pip install -r bin/requirements.txt
```

### Mode file:// (sans serveur)

Aucune fonctionnalité réseau (traduction, YouTube) n'est disponible dans ce mode.

```bash
# Générer les fichiers .js (une fois, puis après chaque modification .sqlite/.json)
python3 bin/sqlite2js.py

# Ouvrir directement dans le navigateur
xdg-open Exam-Prep.html     # Linux
open Exam-Prep.html          # macOS
start Exam-Prep.html         # Windows
```

### Mode serveur HTTP local

Toutes les fonctionnalités sont disponibles : traduction Claude, génération YouTube, OpenAI, Mistral, Ollama.

```bash
python3 bin/serve.py                       # localhost:8080
python3 bin/serve.py --port 3000           # port personnalisé
python3 bin/serve.py --host 0.0.0.0        # exposer sur le réseau local

# Ouvrir : http://localhost:8080/Exam-Prep.html
```

### Mode Docker (test local en container)

```bash
# Construire l'image
docker build -t exam-prep-local .

# Lancer le container
docker run -p 8080:8080 exam-prep-local

# Ouvrir : http://localhost:8080/Exam-Prep.html
```

L'image `python:3.12-slim` embarque `yt-dlp` et lance `serve.py` directement
sur le port 8080 — pas de nginx nécessaire pour le test local.

---

## 4. Structure des bases de données SQLite

### 4.1 Base de contenu — `data/content/<id>.sqlite`

#### Table `questions`

Schéma minimal (CDMP, AI-900) — 4 options :

| Colonne | Type | Contrainte | Description |
|---------|------|-----------|-------------|
| `id` | INTEGER | PK AUTOINCREMENT | Identifiant unique |
| `domain` | TEXT | NOT NULL | Domaine / thème |
| `question` | TEXT | NOT NULL | Texte de la question |
| `opt_a`…`opt_d` | TEXT | NOT NULL | Options de réponse |
| `correct_idx` | TEXT | NOT NULL | Index de la bonne réponse (voir note) |
| `explanation` | TEXT | NOT NULL | Explication affichée après réponse |
| `is_complex` | INTEGER | NOT NULL DEFAULT 0 | Réservé |

Schéma étendu (DP-300, AZ-104, DP-700, examens personnalisés) — 6 options + multi-select :

| Colonne | Type | Contrainte | Description |
|---------|------|-----------|-------------|
| `opt_e` | TEXT | DEFAULT '' | Option E (vide si inutilisée) |
| `opt_f` | TEXT | DEFAULT '' | Option F (vide si inutilisée) |
| `is_multi` | INTEGER | NOT NULL DEFAULT 0 | 1 = question à choix multiples |
| `select_count` | INTEGER | NOT NULL DEFAULT 1 | Nombre de réponses attendues |

> **Note `correct_idx`** : index 0-based pour les questions simples (`"2"`),
> chaîne séparée par virgules pour le multi-select (`"0,2"`). Stocké en TEXT.
> En mémoire, le moteur remplace l'index par un hash SHA-1 du texte de l'option
> pour éviter de révéler la réponse via l'inspection du DOM.

**Index :** `uq_q UNIQUE ON (question)` — pas de doublons.

#### Table `meta`

| key | Exemple | Rôle |
|-----|---------|------|
| `version` | `"4"` | Incrémenter force le rechargement du cache IndexedDB |
| `question_count` | `"546"` | Nombre de questions (pour l'affichage) |
| `base_lang` | `"fr"` | Langue de base de l'examen — détermine la tuile de langue affichée et la référence pour les traductions. Écrit automatiquement lors de la génération YouTube/Markdown. |

#### Table `question_translations`

Créée à la demande lors de la première traduction (Claude Haiku).

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

Ajoutées dans la base de contenu par `ensureResultsTables()` au premier chargement.

#### Table `sessions`

| Colonne | Type | Description |
|---------|------|-------------|
| `id` | INTEGER PK | Identifiant de session |
| `started_at` | TEXT | Horodatage ISO 8601 — clé de déduplication à l'import |
| `completed_at` | TEXT | Horodatage de fin |
| `score` | INTEGER | Bonnes réponses |
| `attempted` | INTEGER | Questions répondues (hors skip) |
| `duration_sec` | INTEGER | Durée nette en secondes |
| `quiz_id` | TEXT | Identifiant de l'examen |
| `quiz_title` | TEXT | Titre affiché |
| `total_questions` | INTEGER | Taille du tirage |

#### Table `domain_scores`

Scores par domaine pour chaque session (`session_id`, `domain`, `correct`, `total`).

#### Table `session_answers`

Réponse fournie pour chaque question (`session_id`, `question_id`, `question_idx`,
`question`, `domain`, `answer_given`, `correct_answer`, `is_correct`, `explanation`).

> **Mode adaptatif** : interroge les 3 dernières sessions et identifie les questions
> répondues correctement ≥ 2 fois (pool « maîtrisées », 15 % du tirage).
> Les autres constituent le pool « à réviser » (85 %).

---

### 4.3 Base d'historique exportée — `data/results/<id>_history.sqlite`

Tables : `sessions`, `domain_scores`, `session_answers`, `meta`.
Utilisée pour pré-charger l'historique au premier démarrage d'un examen.

---

## 5. Format des fichiers de configuration

### `exams/index.json`

```json
{ "exams": ["cdmp", "ai900", "dp300", "az104", "dp700"] }
```

### `exams/<id>.json`

```json
{
  "id":            "dp300",
  "title":         "DP-300",
  "subtitle":      "Azure Database Administrator Associate",
  "description":   "Description HTML (balises autorisées)",
  "version":       4,
  "perExam":       55,
  "timeMin":       100,
  "passThreshold": 70,
  "cssClass":      "dp300",
  "contentFile":   "dp300.sqlite",
  "resultsFile":   "dp300_history.sqlite"
}
```

| Champ | Description |
|-------|-------------|
| `version` | Incrémenter force le rechargement du cache IndexedDB |
| `perExam` | Nombre de questions par défaut |
| `passThreshold` | Score de réussite en % |
| `cssClass` | Classe CSS pour la couleur d'accentuation |

---

## 6. Scripts utilitaires

### `bin/serve.py`

Serveur HTTP + proxy API. Requis pour la traduction, les transcripts YouTube et Ollama.

```bash
python3 bin/serve.py [--port PORT] [--host HOST] [--cors-origin ORIGIN]
```

| Option | Défaut | Description |
|--------|--------|-------------|
| `--port` | `8080` | Port d'écoute |
| `--host` | `127.0.0.1` | Interface réseau (`0.0.0.0` pour le réseau local) |
| `--cors-origin` | `*` | Origine CORS autorisée (restreindre en production) |

Endpoints publics :

| Méthode | Chemin | Description |
|---------|--------|-------------|
| GET | `/*` | Fichiers statiques depuis la racine du projet |
| POST | `/api/translate` | Proxy vers `api.anthropic.com/v1/messages` (Anthropic) |
| POST | `/api/openai` | Proxy vers `api.openai.com/v1/chat/completions` (OpenAI) |
| POST | `/api/mistral` | Proxy vers `api.mistral.ai/v1/chat/completions` (Mistral) |
| POST | `/api/transcript` | Extraction de sous-titres YouTube via yt-dlp |
| POST | `/api/ollama` | Proxy vers une instance Ollama locale |

Les trois proxies IA (`/api/translate`, `/api/openai`, `/api/mistral`) reçoivent le
corps en format Anthropic-like `{model, max_tokens, system, messages}` et normalisent
la réponse vers `{content:[{text:"..."}]}`. Le client lit toujours `data.content[0].text`.
La clé API est transmise via l'en-tête `X-Api-Key` et n'est jamais stockée côté serveur.

Endpoints d'administration (voir §12) — authentification `Bearer` requise sauf mention :

| Méthode | Chemin | Auth | Description |
|---------|--------|------|-------------|
| GET | `/api/admin/salt` | — | Retourne le sel et le flag `first_login` |
| GET | `/api/admin/env` | — | Détection container (bannière dans l'UI) |
| GET | `/api/admin/exams` | ✓ | Liste des examens (natifs + uploadés) |
| GET | `/api/admin/questions` | ✓ | Questions paginées (`?exam=&search=&page=&per_page=`) |
| GET | `/api/admin/question` | ✓ | Question unique (`?exam=&id=`) |
| GET | `/api/admin/export` | ✓ | Téléchargement binaire du SQLite (`?exam=`) |
| POST | `/api/admin/update-question` | ✓ | Modifier une question |
| POST | `/api/admin/change-password` | ✓ | Changer le mot de passe admin |
| POST | `/api/admin/upload-exam` | ✓ | Importer un SQLite (base64) et créer `exams/<id>.json` |
| POST | `/api/admin/apply-updates` | ✓ | Appliquer des mises à jour générées par IA (`{exam, updated, new}`) |

`GET /data/admin.js` est bloqué avec un 403.

**Clés API par fournisseur** — chaque clé est stockée dans `sessionStorage` du
navigateur (effacée à la fermeture de l'onglet) sous des clés séparées :

| Fournisseur | Clé `sessionStorage` |
|-------------|----------------------|
| Anthropic | `_ak` |
| OpenAI | `_ak_openai` |
| Mistral | `_ak_mistral` |

> **Sécurité** : en production, passer `--cors-origin https://votre-domaine.com`
> pour restreindre l'accès aux proxies API à votre seule origine.

### `bin/sqlite2js.py`

Convertit les fichiers de données en modules `.js` pour le mode `file://`.

```bash
python3 bin/sqlite2js.py            # conversion unique
python3 bin/sqlite2js.py --watch    # surveille et reconvertit automatiquement
python3 bin/sqlite2js.py --clean    # supprime les .js générés
```

À relancer après toute modification d'un `.sqlite` ou `.json`.

### `bin/get_playlist_transcripts.py`

Télécharge les sous-titres d'une playlist YouTube et les convertit en `.txt`.

```bash
# Prérequis
pip install yt-dlp

python3 bin/get_playlist_transcripts.py <playlist_url> [options]
```

| Option | Défaut | Description |
|--------|--------|-------------|
| `--output DIR` | `./transcripts` | Dossier de sortie |
| `--lang CODE` | `fr` | Code langue des sous-titres (`fr`, `en`…) |

```bash
# Exemple
python3 bin/get_playlist_transcripts.py \
  "https://youtube.com/playlist?list=PLxxxxx" \
  --output transcripts/az104 \
  --lang fr
```

### `bin/transcript2questions.py`

Génère des questions QCM depuis des fichiers de transcripts via Claude.

```bash
python3 bin/transcript2questions.py \
    --input transcripts/az104 \
    --output data/content/az104_custom.sqlite \
    --exam-id az104_custom \
    --api-key sk-ant-... \
    [--model claude-haiku-4-5-20251001] \
    [--questions-per-chunk 5] \
    [--chunk-words 1500] \
    [--append]
```

| Option | Défaut | Description |
|--------|--------|-------------|
| `--input DIR` | — | Dossier contenant les `.srt` ou `.txt` |
| `--output FILE` | — | Chemin du SQLite de sortie |
| `--exam-id ID` | `custom` | Identifiant stocké dans `meta` |
| `--api-key KEY` | `$ANTHROPIC_API_KEY` | Clé API Anthropic |
| `--model MODEL` | `claude-haiku-4-5-20251001` | Modèle Claude |
| `--questions-per-chunk N` | `5` | Questions générées par segment |
| `--chunk-words N` | `1500` | Taille max d'un segment en mots |
| `--append` | — | Ajouter à une base existante |

---

## 7. Pipeline YouTube → QCM

Deux approches selon le volume.

### A. Génération directe depuis l'interface (une vidéo ou une URL)

Dans le picker, cliquer **➕ Ajouter un examen** → onglet **▶ YouTube**.

1. Coller une URL YouTube (vidéo ou playlist)
2. Sélectionner la langue des sous-titres et le modèle (voir tableau ci-dessous)
3. Saisir la clé API du fournisseur choisi si elle n'est pas déjà mémorisée
4. Cliquer **Créer**

| Groupe | Modèles disponibles |
|--------|---------------------|
| **Claude (Anthropic)** | Haiku 4.5 — rapide · Sonnet 4.6 — qualité |
| **OpenAI** | GPT-4o mini — rapide · GPT-4o — qualité |
| **Mistral** | Mistral Small — rapide · Mistral Large — qualité |
| **Local** | Ollama (URL + nom de modèle configurables) |

La clé est validée avant tout téléchargement. Elle est stockée dans `sessionStorage`
du navigateur uniquement — jamais côté serveur, et effacée automatiquement à la
fermeture de l'onglet ou du navigateur (voir §6 pour les clés par fournisseur).

> Nécessite le mode serveur HTTP (`python3 bin/serve.py` ou container Docker).

### B. Pipeline en ligne de commande (playlists volumineuses)

```bash
# Étape 1 — Télécharger les sous-titres
python3 bin/get_playlist_transcripts.py \
  "https://youtube.com/playlist?list=PLxxxxx" \
  --output transcripts/mon-examen \
  --lang fr

# Étape 2 — Générer les questions
python3 bin/transcript2questions.py \
  --input  transcripts/mon-examen \
  --output data/content/mon-examen.sqlite \
  --exam-id mon-examen \
  --api-key sk-ant-...

# Étape 3 — Générer les fichiers .js (pour le mode file://)
python3 bin/sqlite2js.py

# Étape 4 — Déclarer l'examen
# Ajouter "mon-examen" dans exams/index.json
# Créer exams/mon-examen.json avec title, perExam, timeMin, passThreshold, contentFile
```

### Support Ollama (modèle local)

Pour la génération de questions sans clé API cloud :

1. Dans la modale "Ajouter un examen" → onglet YouTube, sélectionner **Ollama** dans le groupe *Local*
2. Renseigner l'URL Ollama (défaut : `http://localhost:11434`) et le nom du modèle
3. `serve.py` proxifie la requête vers Ollama (`POST /api/ollama`)

---

## 8. Ajouter un examen

### Depuis un fichier SQLite existant

1. Déposer `data/content/monexamen.sqlite` (schéma §4.1)
2. Créer `exams/monexamen.json`
3. Ajouter `"monexamen"` dans `exams/index.json`
4. `python3 bin/sqlite2js.py`

### Depuis l'interface (examen personnalisé)

**➕ Ajouter un examen** → onglet **📁 Fichier** : importer un `.sqlite` ou créer
une base vide. Les métadonnées sont dans `localStorage`, la base dans IndexedDB.

### Schéma SQLite minimal

```sql
CREATE TABLE questions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    domain       TEXT    NOT NULL DEFAULT 'General',
    question     TEXT    NOT NULL,
    opt_a        TEXT    NOT NULL DEFAULT '',
    opt_b        TEXT    NOT NULL DEFAULT '',
    opt_c        TEXT    NOT NULL DEFAULT '',
    opt_d        TEXT    NOT NULL DEFAULT '',
    opt_e        TEXT             DEFAULT '',
    opt_f        TEXT             DEFAULT '',
    correct_idx  TEXT    NOT NULL DEFAULT '0',
    explanation  TEXT    NOT NULL DEFAULT '',
    is_complex   INTEGER NOT NULL DEFAULT 0,
    is_multi     INTEGER NOT NULL DEFAULT 0,
    select_count INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT INTO meta VALUES ('version', '1');
INSERT INTO meta VALUES ('question_count', '0');
```

---

## 9. Export et import de données

### Depuis l'écran de démarrage (par examen)

| Bouton | Contenu |
|--------|---------|
| 📥 Exporter la base | Questions + traductions + historique complet |
| 📤 Importer une base | Remplace la base active en IndexedDB |

### Depuis l'écran d'historique

| Bouton | Contenu |
|--------|---------|
| 📥 Sauvegarder l'historique | Sessions + scores + réponses, sans questions |
| 📤 Restaurer un historique | Fusion avec déduplication sur `started_at` |

Le fichier d'historique exporté peut être pré-chargé en le déposant dans
`data/results/<id>_history.sqlite` et en relançant `sqlite2js.py`.

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
  │ 1. window.__EXAM_INDEX              │  déjà en mémoire
  │ 2. loadScript(exams/index.js)       │  file:// ✓
  │ 3. fetch(exams/index.json)          │  HTTP uniquement
  │ Pour chaque id :                    │
  │   a. window.__EXAM_CONFIGS[id]      │
  │   b. loadScript(exams/<id>.js)      │  file:// ✓
  │   c. fetch(exams/<id>.json)         │  HTTP uniquement
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
  │   1. window.__EXAM_CONTENT[file]  (mémoire)         │
  │   2. loadScript(content/<file>.js) (file:// ✓)      │
  │   3. fetch(data/content/<file>)   (HTTP)             │
  │   4. _promptManualImport()        (sélection fichier)│
  │       │                                             │
  │       ▼                                             │
  │ _loadDataAsset(resultsFile) [si existe]             │
  │   → _mergeResultsInto() si trouvé                   │
  │       │                                             │
  │       ▼                                             │
  │ ensureResultsTables() + persistDB(IDB)              │
  └─────────────────────────────────────────────────────┘
        │
        ▼
showLangScreen() ──▶ showConfigScreen() ──▶ startExam()
```

### Cache IndexedDB

Chaque base est mise en cache sous `<id>_db`. La version en cache est comparée
à `meta.version` : si inférieure, la base est rechargée depuis la source.
Pour forcer un rechargement, incrémenter `version` dans le `.json` et relancer `sqlite2js.py`.

---

## 11. Déploiement Kubernetes

### Architecture dans le container de production

En production, l'image embarque nginx + serve.py dans le même container :

```
[navigateur]
    │ HTTPS
    ▼
[ingress-nginx]  ──  TLS terminé par cert-manager
    │
    ▼  /prep-exam/
[nginx :80]  ──  fichiers statiques → /usr/share/nginx/html/prep-exam/
    │
    │  /prep-exam/api/*  →  proxy_pass  →  127.0.0.1:8081
    ▼
[serve.py :8081]  ──  proxy Anthropic / yt-dlp / Ollama
```

### Arborescence du répertoire `deploy/`

```
deploy/
├── ansible.cfg                            Configuration Ansible locale
├── inventory.ini                          Inventaire (localhost)
├── group_vars/
│   └── all.yml                            Variables : kind_cluster_name, kubeconfig_path, demo_namespace…
├── deploy-k8s.yml                         Playbook principal
└── roles/exam_prep/
    ├── files/
    │   ├── Dockerfile.k8s                 Image Alpine + nginx + yt-dlp
    │   └── nginx-exam.conf                Config nginx (proxy /api/* → serve.py:8081)
    ├── tasks/main.yml                     Tâches Ansible
    └── templates/
        ├── exam-prep-manifests.yaml.j2    Deployment + Service + Ingress
        └── start.sh.j2                    Script démarrage (--cors-origin paramétré)
```

### Prérequis

- Docker installé et daemon démarré
- `kind` dans `~/.local/bin/` (ou adapter `local_bin_dir` dans `group_vars/all.yml`)
- `kubectl` dans `~/.local/bin/`
- Ansible (`pip install ansible`)
- Cluster Kind existant nommé `cnpg-playground` (ou adapter `kind_cluster_name`)
- Namespace `cnpg-demo` existant dans le cluster (ou adapter `demo_namespace`)
- `ingress-nginx` et `cert-manager` déployés dans le cluster

### Déploiement

```bash
cd deploy/
ansible-playbook deploy-k8s.yml -e ingress_domain=votre-domaine.com
```

Le playbook effectue dans l'ordre :

1. Copie temporaire de `Dockerfile.k8s` et `nginx-exam.conf` dans la racine du dépôt (contexte Docker)
2. Génère `start.sh` depuis `start.sh.j2` avec le domaine cible
3. `docker build -f Dockerfile.k8s -t cnpg-exam-prep:latest .`
4. Nettoyage des fichiers temporaires
5. `kind load docker-image cnpg-exam-prep:latest --name <kind_cluster_name>`
6. Génération et application des manifestes Kubernetes (Deployment + Service + Ingress)
7. `kubectl rollout restart deployment/exam-prep`
8. Attente du rollout (`--timeout=120s`)

### Personnalisation

Les variables par défaut sont dans `deploy/group_vars/all.yml` :

| Variable | Défaut | Description |
|---|---|---|
| `local_bin_dir` | `~/.local/bin` | Répertoire contenant `kind` et `kubectl` |
| `kind_cluster_name` | `cnpg-playground` | Nom du cluster Kind cible |
| `kubeconfig_path` | `~/.kube/config-<cluster>` | Kubeconfig dédié |
| `demo_namespace` | `cnpg-demo` | Namespace de déploiement |
| `ingress_domain` | _(vide)_ | Domaine public — **obligatoire via `-e`** |

Toutes ces variables peuvent être surchargées en ligne de commande :

```bash
ansible-playbook deploy-k8s.yml \
  -e ingress_domain=mon-domaine.com \
  -e kind_cluster_name=mon-cluster \
  -e demo_namespace=mon-namespace
```

### Manifestes Kubernetes

**Deployment** — 1 replica, `imagePullPolicy: Never` (image locale Kind), requests `50m/64Mi`, limits `200m/128Mi`.

**Service** — `ClusterIP` sur le port 80.

**Ingress** — règle `Prefix /prep-exam` vers le service. Pas de bloc `tls:` dans cet ingress — le TLS est géré par un ingress séparé (frontend) pour éviter le conflit de certificat dans nginx-ingress lorsque plusieurs ingresses partagent le même host.

### Sécurité de la clé API

- Stockée dans `sessionStorage` du navigateur — effacée automatiquement à la fermeture de l'onglet ou du navigateur
- Transmise en header `X-Api-Key` via HTTPS, jamais loggée ni stockée côté serveur
- Validée par un appel test minimal (1 token) avant tout téléchargement de sous-titres
- `--cors-origin https://{{ ingress_domain }}` restreint le proxy `/api/*` à votre seule origine

---

## 12. Interface d'administration

`admin.html` est une page séparée accessible à `/prep-exam/admin.html` (ou `admin.html`
en local). Elle permet de corriger manuellement des questions dans n'importe quel
examen et d'importer des examens personnalisés depuis le navigateur.

### Accès

```
https://votre-domaine.com/prep-exam/admin.html
http://localhost:8080/admin.html     # mode serveur Python local
```

> Requiert le mode serveur HTTP. L'admin ne fonctionne pas en `file://`.

### Authentification

Au premier chargement, une page de connexion demande un mot de passe.

| Étape | Mécanique |
|-------|-----------|
| Récupération du sel | `GET /api/admin/salt` → `{salt, first_login}` |
| Calcul du token | `SHA-256(salt + mot_de_passe)` côté navigateur |
| Vérification | `GET /api/admin/exams` avec `Authorization: Bearer <token>` |
| Session | Token conservé dans `sessionStorage` — effacé à la fermeture de l'onglet |

Le mot de passe par défaut est **`admin`**. Les credentials sont dans `data/admin.js` :

```js
window.__ADMIN_CREDS = {"salt": "...", "hash": "...", "first_login": true};
```

Ce fichier est bloqué en HTTP (403) — nginx et `serve.py` le refusent tous les deux.
Il n'est jamais transmis au navigateur ; `serve.py` le lit directement depuis le
système de fichiers du container.

### Changement de mot de passe obligatoire

Si `first_login: true` est présent dans `data/admin.js`, l'interface affiche le
modal de changement de mot de passe en mode forcé après la connexion :
- Le bouton "Annuler" est masqué
- Il est impossible d'accéder au dashboard sans changer le mot de passe

Après le changement, `serve.py` réécrit `data/admin.js` avec `first_login: false`
et un nouveau sel + hash générés côté navigateur.

Pour **réinitialiser** le mot de passe au défaut (`admin`), remplacer `data/admin.js` :

```js
window.__ADMIN_CREDS = {"salt": "7892f03b3797f690e5624999f7d7e63e", "hash": "331b3dc53cfb262398a2e21563332222d1b66c02b443a60d995c346d92e9ae0f", "first_login": true};
```

Puis redéployer l'image (le fichier est copié dans le container au build).

### Fonctionnalités du dashboard

#### Recherche et pagination

- Sélecteur d'examen (examens natifs + examens uploadés marqués `↑`)
- Champ de recherche en texte libre sur la question et le domaine (debounce 380 ms)
- Pagination par 50 questions

#### Modification d'une question

Cliquer **Modifier** sur une ligne ouvre un panneau latéral avec :
- Champ domaine
- Énoncé de la question
- Options A–F (radio pour question simple, checkboxes pour multi-select)
- Checkbox "Choix multiples" + champ "Nombre de bonnes réponses"
- Explication

La sauvegarde appelle `POST /api/admin/update-question` et incrémente
automatiquement le champ `version` dans `exams/<id>.json` pour invalider le
cache IndexedDB des clients.

> **Avertissement container** : une bannière signale que les modifications sont
> stockées dans le container actif et perdues au prochain redéploiement. Utiliser
> **⬇ Exporter SQLite** avant de redéployer, puis committer le fichier dans le dépôt.

### Importer un examen personnalisé

Le bouton **↑ Importer** dans la toolbar ouvre un modal avec deux onglets.

#### Onglet "Depuis l'application"

Liste les examens personnalisés créés via **➕ Ajouter un questionnaire** dans
l'application principale (même navigateur, même origine). La liste est lue depuis
`localStorage._exam_custom_quizzes_v1`. La sélection d'un examen remplit
automatiquement l'ID et le titre.

Au clic sur "↑ Importer" :
1. Le SQLite est lu depuis IndexedDB (`exam_prep_v1` / store `sqlite`, clé `<id>_db`)
2. Encodé en base64 et envoyé via `POST /api/admin/upload-exam`
3. `serve.py` le sauvegarde dans `data/content/<id>.sqlite` et crée `exams/<id>.json`
4. L'examen apparaît immédiatement dans le sélecteur avec le préfixe `↑`

#### Onglet "Depuis un fichier"

Sélection directe d'un fichier `.sqlite` depuis le disque. L'ID est pré-rempli
depuis le nom du fichier (caractères invalides remplacés par `_`).

#### Contraintes sur l'ID

L'ID doit correspondre à `^[a-z0-9_-]{1,64}$`. Si l'ID d'un examen personnalisé
(`custom_1234567890`) respecte déjà ce format, il peut être réutilisé tel quel.

### Mettre à jour un examen avec du nouveau contenu

Bouton **🔄 Mettre à jour** dans la toolbar (visible dès qu'un examen est sélectionné).
Ouvre un modal identique à la création, avec deux onglets source.

#### Sources disponibles

| Onglet | Entrée |
|--------|--------|
| **▶ YouTube** | URL vidéo ou playlist — sous-titres téléchargés via yt-dlp |
| **📄 Markdown** | Fichier `.md` ou texte collé directement |

Contrôles communs : langue du contenu, nombre de questions par segment (défaut : 5),
modèle (Claude / OpenAI / Mistral / Ollama), clé API du fournisseur choisi ou
paramètres Ollama. Les mêmes fournisseurs que la création sont disponibles.

#### Déroulement

1. Chargement des questions existantes (`GET /api/admin/questions?per_page=500`)
2. Validation de la clé API (appel test 1 token)
3. Téléchargement des sous-titres ou lecture du Markdown
4. Génération segment par segment avec un prompt de mise à jour (voir ci-dessous)
5. Application via `POST /api/admin/apply-updates` → bump de version (invalide le cache IndexedDB)
6. Rechargement du tableau

#### Prompt de mise à jour

Le prompt système (`_QUP_SYSTEM`) diffère du prompt de création sur trois points :

- **Contexte existant** — les 200 premières questions (id | domaine | énoncé tronqué à 120 car.)
  sont injectées dans chaque appel pour éviter les doublons et permettre la mise à jour ciblée.
- **Mission A — Mise à jour** — si le nouveau contenu contredit ou précise une question
  existante, le modèle fournit la version corrigée avec son `id`. Les autres questions
  ne sont pas touchées.
- **Mission B — Enrichissement** — nouvelles questions uniquement sur les sujets
  non encore couverts par les questions existantes.

#### Règles sur les perturbateurs (incluses dans le prompt)

- Même catégorie que la bonne réponse (jamais hors-sujet ni absurde)
- Représenter des erreurs réelles du domaine : confusion terminologique, inversion de priorité,
  valeur seuil décalée, généralisation excessive, amalgame entre concepts proches
- Longueur et style identiques à la bonne réponse
- Explication obligatoirement comparative (pourquoi chaque perturbateur est incorrect)
- Interdiction de "Aucune de ces réponses" et "Toutes les réponses ci-dessus"

Si le même `id` est mis à jour dans plusieurs segments, la dernière version reçue gagne
(déduplication côté client avant envoi à `apply-updates`).

### Exporter un SQLite corrigé

Bouton **⬇ Exporter SQLite** (visible dès qu'un examen est sélectionné) : télécharge
le fichier `data/content/<id>.sqlite` directement depuis le serveur.

**Nom du fichier** : `<Titre_de_l_examen>_YYYYMMDD_HHmmss.sqlite`
— espaces et caractères spéciaux remplacés par `_`, underscores consécutifs fusionnés,
horodatage local au moment du clic.

Exemples :
```
DP_300_20260625_143022.sqlite
Azure_Database_Administrator_Associate_20260625_143022.sqlite
Accord_du_participe_passé_20260625_143022.sqlite
```

À committer dans `data/content/<id>.sqlite` (sans le timestamp dans le dépôt)
puis redéployer pour rendre les corrections permanentes.
