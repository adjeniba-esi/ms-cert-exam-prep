-- =============================================================================
-- 00_full_schema.sql
-- Schéma complet d'une base de contenu avec historique et traductions
-- =============================================================================
-- Ce script crée la totalité des tables en une seule passe.
-- Il correspond à une base data/content/<id>.sqlite après qu'au moins un examen
-- a été passé et qu'une traduction a été effectuée.
--
-- Utilisation :
--   sqlite3 mon_examen.sqlite < sql/00_full_schema.sql
--
-- Pour les scripts détaillés avec commentaires complets, voir :
--   sql/01_questions.sql      Banque de questions
--   sql/02_history.sql        Tables d'historique (sessions, réponses)
--   sql/03_translations.sql   Traductions multilingues
--   sql/04_history_export.sql Schéma du fichier d'export historique seul
-- =============================================================================

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ── Banque de questions ───────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS questions (
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

CREATE UNIQUE INDEX IF NOT EXISTS uq_question    ON questions (question);

-- ── Traductions ───────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS question_translations (
    question_id  INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    lang         TEXT    NOT NULL,
    question     TEXT    NOT NULL DEFAULT '',
    opt_a        TEXT    NOT NULL DEFAULT '',
    opt_b        TEXT    NOT NULL DEFAULT '',
    opt_c        TEXT    NOT NULL DEFAULT '',
    opt_d        TEXT    NOT NULL DEFAULT '',
    opt_e        TEXT             DEFAULT '',
    opt_f        TEXT             DEFAULT '',
    explanation  TEXT    NOT NULL DEFAULT '',
    PRIMARY KEY (question_id, lang)
);

CREATE INDEX IF NOT EXISTS idx_trans_lang        ON question_translations (lang);

-- ── Historique des sessions ───────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at      TEXT    NOT NULL,
    completed_at    TEXT    NOT NULL,
    score           INTEGER NOT NULL,
    attempted       INTEGER NOT NULL,
    cx_correct      INTEGER          DEFAULT 0,
    cx_total        INTEGER          DEFAULT 0,
    duration_sec    INTEGER          DEFAULT 0,
    quiz_id         TEXT             DEFAULT '',
    quiz_title      TEXT             DEFAULT '',
    total_questions INTEGER          DEFAULT 0
);

CREATE TABLE IF NOT EXISTS domain_scores (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    domain     TEXT    NOT NULL,
    correct    INTEGER NOT NULL,
    total      INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ds_sid            ON domain_scores (session_id);

CREATE TABLE IF NOT EXISTS session_answers (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id     INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    question_id    INTEGER          DEFAULT NULL,
    question_idx   INTEGER NOT NULL DEFAULT 0,
    question       TEXT    NOT NULL DEFAULT '',
    domain         TEXT    NOT NULL DEFAULT '',
    answer_given   TEXT             DEFAULT NULL,
    correct_answer TEXT    NOT NULL DEFAULT '',
    is_correct     INTEGER NOT NULL DEFAULT 0,
    explanation    TEXT    NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_ans_sid           ON session_answers (session_id);
CREATE INDEX IF NOT EXISTS idx_ans_adapt
    ON session_answers (question_id, session_id, is_correct)
    WHERE question_id IS NOT NULL;

-- ── Métadonnées ───────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY NOT NULL,
    value TEXT NOT NULL
);

INSERT OR IGNORE INTO meta (key, value) VALUES ('version',        '1');
INSERT OR IGNORE INTO meta (key, value) VALUES ('question_count', '0');
