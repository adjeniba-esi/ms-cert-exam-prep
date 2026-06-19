#!/usr/bin/env python3
"""
transcript2questions.py
=======================
Génère des questions QCM depuis des transcripts de vidéos de formation
et les insère dans une base SQLite compatible avec Exam-Prep.html.

Usage :
    python bin/transcript2questions.py \
        --input transcripts/ \
        --output data/content/monexamen.sqlite \
        --exam-id monexamen \
        --api-key sk-ant-... \
        [--model claude-haiku-4-5-20251001] \
        [--questions-per-chunk 5] \
        [--chunk-words 1500] \
        [--append]

Variables d'environnement :
    ANTHROPIC_API_KEY   Clé API Anthropic (alternative à --api-key)
"""
import argparse, json, os, re, sqlite3, sys
import urllib.request, urllib.error, ssl

ANTHROPIC_URL = 'https://api.anthropic.com/v1/messages'
SSL_CTX = ssl.create_default_context()

SCHEMA = """
PRAGMA journal_mode = WAL;
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
CREATE UNIQUE INDEX IF NOT EXISTS uq_question ON questions (question);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY NOT NULL,
    value TEXT NOT NULL
);
"""

SYSTEM_PROMPT = """\
Tu es un expert en création de questionnaires de certification professionnelle.
À partir d'un extrait de transcript de vidéo de formation, génère des questions QCM de haute qualité.

Règles :
- Questions claires et précises, basées UNIQUEMENT sur le contenu fourni
- 4 à 6 options de réponse (les distracteurs doivent être crédibles et plausibles)
- Les questions multi-choix doivent le mentionner explicitement ("Sélectionnez X réponses" / "Select X answers")
- Le champ "domain" doit être un thème court (2-4 mots) représentatif du sujet traité
- L'explication justifie la bonne réponse ET éclaircit pourquoi les autres sont incorrectes
- Même langue que le transcript fourni
- correct_idx : index 0-based de la bonne option ("2"), ou liste pour multi-choix ("0,2")
- opt_e et opt_f : laisser "" si non utilisées

Réponds UNIQUEMENT avec un tableau JSON valide, sans texte autour :
[
  {
    "domain": "Thème court",
    "question": "...",
    "opt_a": "...", "opt_b": "...", "opt_c": "...", "opt_d": "...",
    "opt_e": "", "opt_f": "",
    "correct_idx": "2",
    "explanation": "...",
    "is_multi": 0,
    "select_count": 1
  }
]"""


def clean_srt(text):
    """Retire les numéros de séquence, horodatages et balises HTML d'un fichier SRT."""
    text = re.sub(r'^\d+\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}', '', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def chunk_text(text, max_words=1500):
    """Découpe le texte en segments d'environ max_words mots."""
    paragraphs = [p.strip() for p in re.split(r'\n{2,}', text) if p.strip()]
    chunks, current, count = [], [], 0
    for p in paragraphs:
        words = len(p.split())
        if count + words > max_words and current:
            chunks.append('\n\n'.join(current))
            current, count = [p], words
        else:
            current.append(p)
            count += words
    if current:
        chunks.append('\n\n'.join(current))
    return chunks


def call_claude(api_key, model, chunk, n_questions, title):
    body = json.dumps({
        'model': model,
        'max_tokens': 4096,
        'system': SYSTEM_PROMPT,
        'messages': [{
            'role': 'user',
            'content': (
                f'Vidéo source : "{title}"\n\n'
                f'Génère exactement {n_questions} questions à partir de ce transcript :\n\n'
                f'{chunk}'
            )
        }]
    }).encode()

    req = urllib.request.Request(
        ANTHROPIC_URL,
        data=body,
        headers={
            'Content-Type':      'application/json',
            'x-api-key':         api_key,
            'anthropic-version': '2023-06-01',
        },
        method='POST'
    )
    with urllib.request.urlopen(req, context=SSL_CTX, timeout=120) as resp:
        data = json.loads(resp.read())
    return data['content'][0]['text']


def parse_questions(text):
    """Extrait le tableau JSON de la réponse Claude."""
    m = re.search(r'\[[\s\S]*\]', text)
    if not m:
        raise ValueError('Aucun tableau JSON trouvé dans la réponse')
    return json.loads(m.group())


def insert_questions(conn, questions):
    inserted = skipped = 0
    for q in questions:
        try:
            conn.execute(
                'INSERT INTO questions '
                '(domain,question,opt_a,opt_b,opt_c,opt_d,opt_e,opt_f,'
                'correct_idx,explanation,is_multi,select_count) '
                'VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                (
                    q.get('domain', 'General'),
                    q['question'],
                    q.get('opt_a', ''), q.get('opt_b', ''),
                    q.get('opt_c', ''), q.get('opt_d', ''),
                    q.get('opt_e', ''), q.get('opt_f', ''),
                    str(q.get('correct_idx', '0')),
                    q.get('explanation', ''),
                    int(q.get('is_multi', 0)),
                    int(q.get('select_count', 1)),
                )
            )
            inserted += 1
        except sqlite3.IntegrityError:
            skipped += 1
    conn.commit()
    return inserted, skipped


def main():
    ap = argparse.ArgumentParser(
        description='Génère des QCM depuis des transcripts SRT/TXT via Claude',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    ap.add_argument('--input',  required=True, metavar='DIR',
                    help='Dossier contenant les fichiers .srt ou .txt')
    ap.add_argument('--output', required=True, metavar='FILE',
                    help='Chemin du fichier SQLite de sortie')
    ap.add_argument('--exam-id', default='custom', metavar='ID',
                    help='Identifiant de l\'examen (stocké dans meta)')
    ap.add_argument('--api-key', default=os.environ.get('ANTHROPIC_API_KEY', ''),
                    metavar='KEY', help='Clé API Anthropic')
    ap.add_argument('--model', default='claude-haiku-4-5-20251001', metavar='MODEL',
                    help='Modèle Claude à utiliser (défaut : claude-haiku-4-5-20251001)')
    ap.add_argument('--questions-per-chunk', type=int, default=5, metavar='N',
                    help='Nombre de questions à générer par segment (défaut : 5)')
    ap.add_argument('--chunk-words', type=int, default=1500, metavar='N',
                    help='Taille max d\'un segment en mots (défaut : 1500)')
    ap.add_argument('--append', action='store_true',
                    help='Ajouter les questions à une base existante au lieu de la recréer')
    args = ap.parse_args()

    if not args.api_key:
        print('Erreur : clé API manquante. Utilise --api-key ou la variable ANTHROPIC_API_KEY.',
              file=sys.stderr)
        sys.exit(1)

    if not os.path.isdir(args.input):
        print(f'Erreur : dossier introuvable : {args.input}', file=sys.stderr)
        sys.exit(1)

    # Prépare la base SQLite
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    if not args.append and os.path.exists(args.output):
        os.remove(args.output)
    conn = sqlite3.connect(args.output)
    conn.executescript(SCHEMA)
    conn.execute("INSERT OR IGNORE INTO meta VALUES ('exam_id', ?)", (args.exam_id,))
    conn.commit()

    # Collecte les fichiers transcript (.txt prioritaire sur .srt du même nom)
    seen, files = set(), []
    for fname in sorted(os.listdir(args.input)):
        base = os.path.splitext(fname)[0]
        ext  = os.path.splitext(fname)[1].lower()
        if ext == '.txt':
            seen.add(base)
            files.append(fname)
    for fname in sorted(os.listdir(args.input)):
        base = os.path.splitext(fname)[0]
        ext  = os.path.splitext(fname)[1].lower()
        if ext == '.srt' and base not in seen:
            files.append(fname)

    if not files:
        print(f'Aucun fichier .txt/.srt dans {args.input}', file=sys.stderr)
        sys.exit(1)

    total_inserted = total_skipped = 0

    for fname in files:
        fpath = os.path.join(args.input, fname)
        title = re.sub(r'\[.*?\]', '', os.path.splitext(fname)[0]).strip()
        print(f'\n▶ {title}')

        with open(fpath, encoding='utf-8', errors='ignore') as f:
            raw = f.read()

        text = clean_srt(raw) if fname.lower().endswith('.srt') else raw.strip()
        if not text:
            print('  (fichier vide, ignoré)')
            continue

        chunks = chunk_text(text, args.chunk_words)
        total_q = len(chunks) * args.questions_per_chunk
        print(f'  {len(chunks)} segment(s) → ~{total_q} questions attendues')

        for i, chunk in enumerate(chunks, 1):
            print(f'  Segment {i}/{len(chunks)}... ', end='', flush=True)
            try:
                response  = call_claude(args.api_key, args.model, chunk,
                                        args.questions_per_chunk, title)
                questions = parse_questions(response)
                ins, skp  = insert_questions(conn, questions)
                total_inserted += ins
                total_skipped  += skp
                suffix = f', {skp} doublon(s) ignoré(s)' if skp else ''
                print(f'{ins} question(s) insérée(s){suffix}')
            except urllib.error.HTTPError as e:
                print(f'ERREUR API {e.code} : {e.read().decode()[:200]}')
            except Exception as e:
                print(f'ERREUR : {e}')

    # Met à jour les métadonnées
    count = conn.execute('SELECT COUNT(*) FROM questions').fetchone()[0]
    conn.execute("INSERT OR REPLACE INTO meta VALUES ('question_count', ?)", (str(count),))
    conn.execute("INSERT OR REPLACE INTO meta VALUES ('version', '1')")
    conn.commit()
    conn.close()

    print(f'\n✓ Terminé : {total_inserted} question(s) insérée(s), '
          f'{total_skipped} doublon(s) ignoré(s)')
    print(f'  Base : {args.output}  ({count} questions au total)')
    print(f'\nÉtape suivante : déclarer l\'examen dans exams/index.json et exams/{args.exam_id}.json,')
    print( '  puis régénérer les .js miroirs :')
    print( '  python bin/sqlite2js.py')


if __name__ == '__main__':
    main()
