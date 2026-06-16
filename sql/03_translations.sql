-- =============================================================================
-- 03_translations.sql
-- Table des traductions de questions (créée à la demande par l'application)
-- =============================================================================
-- Créée automatiquement lors de la première traduction via Claude Haiku.
-- Stockée dans la même base que les questions (data/content/<id>.sqlite).
-- La traduction est persistée en IndexedDB et réutilisée sans rappel API.
-- =============================================================================

PRAGMA foreign_keys = ON;

-- -----------------------------------------------------------------------------
-- Table : question_translations
-- Traductions des questions, options et explications par langue.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS question_translations (
    question_id  INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    lang         TEXT    NOT NULL, -- code BCP-47 court : 'fr', 'es', 'de'…

    -- Contenu traduit (miroir de la table questions, même colonnes)
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

-- Index pour accélérer le chargement de toutes les traductions d'une langue
CREATE INDEX IF NOT EXISTS idx_trans_lang ON question_translations (lang);

-- =============================================================================
-- Requêtes utiles
-- =============================================================================
/*
-- Récupérer une question en français (avec fallback EN si traduction absente)
SELECT
    COALESCE(t.question,    q.question)    AS question,
    COALESCE(t.opt_a,       q.opt_a)       AS opt_a,
    COALESCE(t.opt_b,       q.opt_b)       AS opt_b,
    COALESCE(t.opt_c,       q.opt_c)       AS opt_c,
    COALESCE(t.opt_d,       q.opt_d)       AS opt_d,
    COALESCE(t.opt_e,       q.opt_e)       AS opt_e,
    COALESCE(t.opt_f,       q.opt_f)       AS opt_f,
    COALESCE(t.explanation, q.explanation) AS explanation
FROM questions q
LEFT JOIN question_translations t
       ON t.question_id = q.id AND t.lang = 'fr'
WHERE q.id = 42;

-- Vérifier la progression de traduction pour une langue
SELECT
    COUNT(*)                                     AS total_questions,
    COUNT(t.question_id)                         AS translated,
    ROUND(100.0 * COUNT(t.question_id) / COUNT(*), 1) AS pct
FROM questions q
LEFT JOIN question_translations t
       ON t.question_id = q.id AND t.lang = 'fr';

-- Supprimer toutes les traductions d'une langue pour forcer la retraduction
DELETE FROM question_translations WHERE lang = 'fr';
*/
