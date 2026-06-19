# Exam Prep — Documentation

Application d'entraînement aux certifications (CDMP, AI-900, DP-300, AZ-104, DP-700).
Chaque examen est autonome : banque de questions SQLite, historique des sessions,
apprentissage adaptatif, traduction multilingue, génération de QCM depuis YouTube.

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

---

## 1. Arborescence

```
./
├── Exam-Prep.html                 Application (fichier unique, ~3000 lignes)
├── Dockerfile                     Image de test local (python:3.12-slim + yt-dlp)
├── .dockerignore
├── .gitattributes                 Force LF sur tous les fichiers texte
│
├── bin/
│   ├── serve.py                   Serveur HTTP + proxy API (traduction, transcripts, Ollama)
│   ├── sqlite2js.py               Convertisseur SQLite/JSON → .js (mode file://)
│   ├── get_playlist_transcripts.py  Télécharge les sous-titres d'une playlist YouTube
│   ├── transcript2questions.py    Génère des QCM depuis des transcripts via Claude
│   └── requirements.txt           Dépendances Python (yt-dlp)
│
├── exams/                         Définitions des examens
│   ├── index.json                 Liste des identifiants d'examens disponibles
│   ├── index.js                   Même contenu, chargeable sans serveur (file://)
│   ├── <id>.json                  Paramètres d'un examen
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
    ├── content/                   Banques de questions (lecture seule)
    │   ├── cdmp.sqlite            600 questions CDMP/DMBOK2
    │   ├── ai900.sqlite           36 questions AI-900
    │   ├── dp300.sqlite           546 questions DP-300
    │   ├── az104.sqlite           123 questions AZ-104
    │   ├── dp700.sqlite           229 questions DP-700
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

Toutes les fonctionnalités sont disponibles : traduction Claude, génération YouTube, Ollama.

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

Endpoints :

| Méthode | Chemin | Description |
|---------|--------|-------------|
| GET | `/*` | Fichiers statiques depuis la racine du projet |
| POST | `/api/translate` | Proxy vers `api.anthropic.com/v1/messages` |
| POST | `/api/transcript` | Extraction de sous-titres YouTube via yt-dlp |
| POST | `/api/ollama` | Proxy vers une instance Ollama locale |

La clé API Anthropic est transmise par le navigateur via l'en-tête `X-Api-Key` et
retransmise sans être stockée côté serveur ni écrite dans les logs.

> **Sécurité** : en production, passer `--cors-origin https://votre-domaine.com`
> pour restreindre l'accès au proxy API à votre seule origine.

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
2. Sélectionner la langue des sous-titres et le modèle (Claude Haiku/Sonnet ou Ollama)
3. Saisir la clé API Anthropic si elle n'est pas déjà mémorisée
4. Cliquer **Créer**

La clé est validée avant tout téléchargement. Elle est stockée dans `localStorage`
du navigateur uniquement — jamais côté serveur.

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

Pour la génération de questions sans clé API Anthropic :

1. Dans la modale "Ajouter un examen" → onglet YouTube, sélectionner **Ollama** dans le sélecteur de modèle
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

### Prérequis

- Cluster Kubernetes avec `ingress-nginx` et `cert-manager`
- `kubectl` et `kind` (pour un cluster local Kind)
- `docker` pour le build de l'image
- Ansible (`ansible-playbook`)

### Image Docker de production

L'image de production (distincte du `Dockerfile` de dev local) est construite
par le playbook Ansible depuis les fichiers dans le dépôt de déploiement.
Elle se base sur `python:3.12-alpine` + `apk add nginx` + `pip install yt-dlp`.

### Déploiement avec Ansible (cluster Kind)

```bash
# Depuis le dépôt de déploiement (cnpg-playground)
ansible-playbook deploy-exam-prep.yml \
  -e ingress_domain=votre-domaine.example.com
```

Le playbook effectue dans l'ordre :

1. Copie le `Dockerfile.exam-prep`, `nginx-exam.conf` et `start.sh` dans le
   répertoire source de l'application
2. `docker build` de l'image `cnpg-exam-prep:latest`
3. Nettoyage des fichiers temporaires copiés
4. `kind load docker-image` pour injecter l'image dans le cluster Kind
5. Génération et application des manifestes Kubernetes (Deployment + Service + Ingress)
6. `kubectl rollout restart deployment/exam-prep`
7. Attente du rollout (`--timeout=120s`)

### Manifestes Kubernetes

**Deployment** — 1 replica, requests `50m/64Mi`, limits `200m/128Mi`.

**Service** — `ClusterIP` sur le port 80.

**Ingress** — règle `Prefix /prep-exam` vers le service. Le bloc `tls:` est géré
par un ingress séparé (frontend) ; ne pas dupliquer `tls:` pour le même host sous
peine de conflit de certificat dans nginx-ingress.

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: exam-prep
spec:
  ingressClassName: nginx
  rules:
  - host: votre-domaine.example.com
    http:
      paths:
      - path: /prep-exam
        pathType: Prefix
        backend:
          service:
            name: exam-prep
            port:
              number: 80
```

### Nginx dans le container

Configuration dans `nginx-exam.conf` (Alpine utilise `/etc/nginx/http.d/`, pas `conf.d/`) :

```nginx
server {
    listen 80;
    root /usr/share/nginx/html;

    location = /prep-exam { return 301 /prep-exam/; }

    location ~ ^/prep-exam(/api/.+)$ {
        proxy_pass         http://127.0.0.1:8081$1;
        proxy_read_timeout 600s;
    }

    location /prep-exam/ { try_files $uri $uri/ =404; }
}
```

### Variables d'environnement et configuration CORS

En production, serve.py est lancé avec l'origine explicite pour restreindre
l'accès au proxy API :

```sh
python bin/serve.py \
  --port 8081 \
  --host 127.0.0.1 \
  --cors-origin https://votre-domaine.example.com
```

Cela garantit que seul le navigateur servi depuis votre domaine peut utiliser
les endpoints `/api/*` comme proxy vers Anthropic.

### Sécurité de la clé API

- Stockée dans `localStorage` du navigateur (scoped à l'origine, inaccessible aux autres sessions)
- Transmise en header `X-Api-Key` via HTTPS, jamais loggée ni stockée côté serveur
- Validée par un appel test minimal (1 token) avant tout téléchargement de sous-titres
