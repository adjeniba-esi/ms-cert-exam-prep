-- =============================================================================
-- 02_history.sql
-- Tables d'historique des sessions d'examen
-- =============================================================================
-- Ces tables sont créées automatiquement par ensureResultsTables() lors du
-- premier chargement d'une base dans l'application. Ce script permet de les
-- créer manuellement ou de recréer une base d'historique vide.
--
-- Deux usages :
--   1. Ajoutées DANS la base de contenu (data/content/<id>.sqlite)
--      → l'historique est colocalisé avec les questions
--   2. Base autonome (data/results/<id>_history.sqlite)
--      → l'historique est séparé des questions (produit par "Sauvegarder l'historique")
-- =============================================================================

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- -----------------------------------------------------------------------------
-- Table : sessions
-- Une ligne par examen passé.
-- Clé métier : started_at (ISO 8601) — utilisée pour la déduplication à l'import.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Horodatages ISO 8601 (ex. '2026-06-09T14:32:11.000Z')
    -- started_at est la clé de déduplication lors de la fusion de fichiers historique :
    -- si la date existe déjà, elle est reculée d'une seconde (jusqu'à 300 tentatives).
    started_at      TEXT    NOT NULL,
    completed_at    TEXT    NOT NULL,

    -- Résultats globaux
    score           INTEGER NOT NULL,           -- nombre de bonnes réponses
    attempted       INTEGER NOT NULL,           -- questions répondues (hors skip)
    cx_correct      INTEGER          DEFAULT 0, -- bonnes réponses aux questions complexes
    cx_total        INTEGER          DEFAULT 0, -- total questions complexes posées
    duration_sec    INTEGER          DEFAULT 0, -- durée nette en secondes (hors pause)

    -- Identification de l'examen source
    quiz_id         TEXT             DEFAULT '', -- ex. 'dp300', 'az104'
    quiz_title      TEXT             DEFAULT '', -- titre affiché (peut être personnalisé)
    total_questions INTEGER          DEFAULT 0   -- taille du tirage
);

-- -----------------------------------------------------------------------------
-- Table : domain_scores
-- Scores détaillés par domaine pour chaque session.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS domain_scores (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    domain     TEXT    NOT NULL,   -- ex. 'Storage', 'Virtual Networking'
    correct    INTEGER NOT NULL,   -- bonnes réponses dans ce domaine
    total      INTEGER NOT NULL    -- questions posées dans ce domaine
);

CREATE INDEX IF NOT EXISTS idx_ds_sid ON domain_scores (session_id);

-- -----------------------------------------------------------------------------
-- Table : session_answers
-- Réponse fournie pour chaque question d'un examen.
-- Permet l'affichage du détail question par question dans l'historique et
-- alimente l'algorithme d'apprentissage adaptatif.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS session_answers (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id     INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,

    -- Lien vers la question source (NULL pour les sessions anciennes ou importées
    -- depuis une base externe sans correspondance de questions)
    -- Utilisé par le mode adaptatif pour identifier les questions maîtrisées.
    question_id    INTEGER          DEFAULT NULL,

    -- Position dans le tirage (0-based)
    question_idx   INTEGER NOT NULL DEFAULT 0,

    -- Snapshot du contenu au moment de l'examen (dans la langue active)
    question       TEXT    NOT NULL DEFAULT '',
    domain         TEXT    NOT NULL DEFAULT '',

    -- Réponse de l'apprenant
    -- NULL  = question passée (skip)
    -- '...' = texte de l'option choisie
    -- 'A | B' = options multiples séparées par ' | '
    answer_given   TEXT             DEFAULT NULL,

    -- Bonne réponse (texte)
    -- Choix unique   : texte de l'option correcte
    -- Choix multiple : textes séparés par ' | '
    correct_answer TEXT    NOT NULL DEFAULT '',

    is_correct     INTEGER NOT NULL DEFAULT 0, -- 1 = bonne réponse, 0 = erreur ou skip

    -- Explication complète (snapshot au moment de l'examen)
    explanation    TEXT    NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_ans_sid ON session_answers (session_id);

-- Pour les requêtes du mode adaptatif :
-- "Questions répondues correctement ≥ 2 fois dans les 3 dernières sessions"
CREATE INDEX IF NOT EXISTS idx_ans_adapt
    ON session_answers (question_id, session_id, is_correct)
    WHERE question_id IS NOT NULL;
