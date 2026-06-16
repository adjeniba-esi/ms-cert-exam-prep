-- =============================================================================
-- 04_history_export.sql
-- Schéma du fichier d'historique exporté (data/results/<id>_history.sqlite)
-- =============================================================================
-- Produit par le bouton "Sauvegarder l'historique" dans l'application.
-- Ne contient PAS les questions, uniquement les résultats des sessions passées.
-- Compatible avec l'import et la fusion (bouton "Restaurer un historique").
--
-- Pour créer une base d'historique vide et compatible :
--   sqlite3 dp300_history.sqlite < sql/04_history_export.sql
-- =============================================================================

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- Même structure que 02_history.sql — copie autonome sans FK vers questions
CREATE TABLE IF NOT EXISTS sessions (
    id              INTEGER PRIMARY KEY,
    started_at      TEXT    NOT NULL,   -- clé de déduplication à l'import
    completed_at    TEXT    NOT NULL,
    score           INTEGER NOT NULL DEFAULT 0,
    attempted       INTEGER NOT NULL DEFAULT 0,
    cx_correct      INTEGER          DEFAULT 0,
    cx_total        INTEGER          DEFAULT 0,
    duration_sec    INTEGER          DEFAULT 0,
    quiz_id         TEXT             DEFAULT '',
    quiz_title      TEXT             DEFAULT '',
    total_questions INTEGER          DEFAULT 0
);

CREATE TABLE IF NOT EXISTS domain_scores (
    id         INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL,
    domain     TEXT    NOT NULL,
    correct    INTEGER NOT NULL DEFAULT 0,
    total      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS session_answers (
    id             INTEGER PRIMARY KEY,
    session_id     INTEGER NOT NULL,
    question_id    INTEGER          DEFAULT NULL,
    question_idx   INTEGER          DEFAULT 0,
    question       TEXT             DEFAULT '',
    domain         TEXT             DEFAULT '',
    answer_given   TEXT             DEFAULT NULL,
    correct_answer TEXT             DEFAULT '',
    is_correct     INTEGER          DEFAULT 0,
    explanation    TEXT             DEFAULT ''
);

-- -----------------------------------------------------------------------------
-- Table : meta
-- Identification du fichier d'export.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY NOT NULL,
    value TEXT NOT NULL
);

INSERT OR IGNORE INTO meta (key, value) VALUES ('version',     '1');
INSERT OR IGNORE INTO meta (key, value) VALUES ('app',         'ExamPrep');
INSERT OR IGNORE INTO meta (key, value) VALUES ('export_date', datetime('now'));

-- =============================================================================
-- Requêtes utiles sur un fichier d'historique
-- =============================================================================
/*
-- Résumé des sessions par examen
SELECT
    quiz_title,
    COUNT(*)                                           AS sessions,
    ROUND(AVG(CAST(score AS REAL) / total_questions * 100), 1) AS avg_score_pct,
    MAX(CAST(score AS REAL) / total_questions * 100)   AS best_pct,
    ROUND(AVG(duration_sec) / 60.0, 1)                AS avg_min
FROM sessions
GROUP BY quiz_id, quiz_title
ORDER BY quiz_title;

-- Taux de réussite par domaine (toutes sessions confondues)
SELECT
    domain,
    SUM(correct)                                            AS total_correct,
    SUM(total)                                              AS total_asked,
    ROUND(100.0 * SUM(correct) / SUM(total), 1)            AS pct
FROM domain_scores
GROUP BY domain
ORDER BY pct ASC;

-- Questions les plus souvent ratées (avec question_id renseigné)
SELECT
    question_id,
    question,
    domain,
    COUNT(*)                                                AS times_asked,
    SUM(is_correct)                                         AS times_correct,
    ROUND(100.0 * SUM(is_correct) / COUNT(*), 1)           AS success_rate_pct
FROM session_answers
WHERE question_id IS NOT NULL
GROUP BY question_id
HAVING times_asked >= 2
ORDER BY success_rate_pct ASC, times_asked DESC
LIMIT 20;

-- Progression dans le temps (score % par session)
SELECT
    started_at,
    quiz_title,
    score,
    total_questions,
    ROUND(100.0 * score / total_questions, 1)               AS score_pct,
    ROUND(duration_sec / 60.0, 1)                           AS duration_min
FROM sessions
ORDER BY started_at ASC;
*/
