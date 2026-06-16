-- =============================================================================
-- 01_questions.sql
-- Schéma canonique d'une banque de questions (data/content/<id>.sqlite)
-- =============================================================================
-- Ce schéma est utilisé par l'application pour tous les examens.
-- Les colonnes opt_e, opt_f, is_multi et select_count sont optionnelles :
-- leur présence est détectée via PRAGMA table_info() au chargement.
-- =============================================================================

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- -----------------------------------------------------------------------------
-- Table : questions
-- Une ligne par question. Les options sont mélangées à chaque tirage (côté JS).
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS questions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Catégorie / thème affiché dans les résultats et l'historique
    domain       TEXT    NOT NULL DEFAULT 'General',

    -- Texte de la question (langue source, généralement EN)
    question     TEXT    NOT NULL,

    -- Options de réponse (A–D obligatoires, E–F optionnels)
    opt_a        TEXT    NOT NULL DEFAULT '',
    opt_b        TEXT    NOT NULL DEFAULT '',
    opt_c        TEXT    NOT NULL DEFAULT '',
    opt_d        TEXT    NOT NULL DEFAULT '',
    opt_e        TEXT             DEFAULT '',   -- 5e option (laisser vide si inutilisée)
    opt_f        TEXT             DEFAULT '',   -- 6e option (laisser vide si inutilisée)

    -- Réponse correcte
    -- • Choix unique   : index 0-based de l'option correcte, ex. '2'
    -- • Choix multiple : index séparés par virgule,           ex. '0,2'
    -- Stocké en TEXT pour supporter les deux formats.
    -- En mémoire, l'application ne stocke jamais cet index directement :
    -- elle calcule un hash(texte_option + sel_interne) pour masquer la réponse.
    correct_idx  TEXT    NOT NULL DEFAULT '0',

    -- Explication affichée après validation de la réponse
    explanation  TEXT    NOT NULL DEFAULT '',

    -- Indicateurs de type
    is_complex   INTEGER NOT NULL DEFAULT 0,   -- réservé (complexité, non utilisé)
    is_multi     INTEGER NOT NULL DEFAULT 0,   -- 1 = question à choix multiples
    select_count INTEGER NOT NULL DEFAULT 1    -- nombre de réponses attendues (is_multi=1)
);

-- Index d'unicité sur le texte de la question (évite les doublons à l'import)
CREATE UNIQUE INDEX IF NOT EXISTS uq_question ON questions (question);

-- -----------------------------------------------------------------------------
-- Table : meta
-- Paires clé/valeur décrivant la banque.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY NOT NULL,
    value TEXT NOT NULL
);

-- Valeurs initiales à adapter à chaque banque
INSERT OR IGNORE INTO meta (key, value) VALUES ('version',        '1');
INSERT OR IGNORE INTO meta (key, value) VALUES ('question_count', '0');

-- =============================================================================
-- Exemples d'insertion
-- =============================================================================
/*
-- Question à choix unique (4 options)
INSERT INTO questions (domain, question, opt_a, opt_b, opt_c, opt_d,
                       correct_idx, explanation)
VALUES (
    'Storage',
    'You need to replicate Azure Blob data across three availability zones '
    'within a single region. Which redundancy option should you choose?',
    'LRS', 'GRS', 'ZRS', 'GZRS',
    '2',   -- ZRS = index 2 (opt_c)
    'Zone-Redundant Storage (ZRS) replicates data synchronously across three '
    'availability zones in a single region.'
);

-- Question à choix multiples (select 2 parmi 5)
INSERT INTO questions (domain, question,
                       opt_a, opt_b, opt_c, opt_d, opt_e,
                       correct_idx, explanation, is_multi, select_count)
VALUES (
    'Compute Resources',
    'You need two PowerShell cmdlets to start and stop an Azure VM on a schedule. '
    'Which two should you use? Each correct answer presents part of the solution.',
    'Start-AzVM', 'Stop-AzVM', 'Restart-AzVM', 'Set-AzVM', 'Suspend-AzVM',
    '0,1',  -- Start-AzVM et Stop-AzVM
    'Start-AzVM starts a VM and Stop-AzVM deallocates it (stops billing for compute).',
    1, 2
);
*/
