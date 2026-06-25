#!/usr/bin/env python3
"""
Exam Prep — Serveur local avec proxy Anthropic API
====================================================
Sert l'application statique (HTML + ./exams + ./data) ET proxifie
les appels à api.anthropic.com pour contourner les restrictions CORS
lors de la traduction des questions.

Ce script se trouve dans ./bin et sert le répertoire PARENT (la racine
du projet) afin que ./exams, ./data/content et ./data/results soient
accessibles via fetch.

Usage :
    python bin/serve.py                  # port 8080 par défaut
    python bin/serve.py --port 3000      # port personnalisé
    python bin/serve.py --host 0.0.0.0   # exposer sur le réseau (ex: conteneur)

Puis ouvrez : http://localhost:8080/Exam-Prep.html
"""
import http.server, urllib.request, urllib.error, ssl, os, sys
import json, re, tempfile, glob, time, base64 as _base64
import sqlite3 as _sqlite3, hashlib as _hashlib
from urllib.parse import urlparse, parse_qs

try:
    import yt_dlp as _yt_dlp
    _YTDLP_OK = True
except ImportError:
    _YTDLP_OK = False

PORT = 8080
HOST = '127.0.0.1'
CORS_ORIGIN = '*'   # remplacé par --cors-origin en production
if '--port' in sys.argv:
    PORT = int(sys.argv[sys.argv.index('--port') + 1])
if '--host' in sys.argv:
    HOST = sys.argv[sys.argv.index('--host') + 1]
if '--cors-origin' in sys.argv:
    CORS_ORIGIN = sys.argv[sys.argv.index('--cors-origin') + 1]

ANTHROPIC_URL = 'https://api.anthropic.com/v1/messages'
SSL_CTX = ssl.create_default_context()

ADMIN_CREDS_FILE = 'data/admin.js'
ADMIN_FIELDS = {'domain','question','opt_a','opt_b','opt_c','opt_d','opt_e','opt_f',
                'correct_idx','explanation','is_multi','select_count'}


def _admin_load_creds():
    try:
        with open(ADMIN_CREDS_FILE, encoding='utf-8') as f:
            m = re.search(r'window\.__ADMIN_CREDS\s*=\s*(\{[^}]+\})', f.read())
            if m:
                return json.loads(m.group(1))
    except Exception:
        pass
    return None


def _admin_verify(handler):
    auth = handler.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return False
    token = auth[7:].strip()
    creds = _admin_load_creds()
    return bool(creds and token == creds.get('hash', ''))


def _admin_list_exams():
    # Bundled exams (from index.json), in their declared order
    known = set()
    exams = []
    try:
        with open('exams/index.json', encoding='utf-8') as f:
            ids = json.load(f).get('exams', [])
        for eid in ids:
            known.add(eid)
            meta = {}
            try:
                with open(f'exams/{eid}.json', encoding='utf-8') as f:
                    meta = json.load(f)
            except Exception:
                pass
            exams.append({'id': eid, 'title': meta.get('title', eid),
                          'subtitle': meta.get('subtitle', ''), 'uploaded': False})
    except Exception:
        pass
    # Uploaded exams: any exams/*.json not listed in index.json
    for path in sorted(glob.glob('exams/*.json')):
        fname = os.path.basename(path)
        if fname == 'index.json':
            continue
        eid = fname[:-5]
        if eid in known:
            continue
        meta = {}
        try:
            with open(path, encoding='utf-8') as f:
                meta = json.load(f)
        except Exception:
            pass
        exams.append({'id': eid, 'title': meta.get('title', eid),
                      'subtitle': meta.get('subtitle', ''), 'uploaded': True})
    return exams


def _admin_apply_updates(exam, updated, new_questions):
    path = f'data/content/{exam}.sqlite'
    if not os.path.exists(path):
        return 400, {'error': 'Examen introuvable'}
    try:
        conn = _sqlite3.connect(path)
        cols = _db_cols(conn)

        updated_count = 0
        for q in updated:
            qid = q.get('id')
            if not isinstance(qid, (int, float)) or int(qid) <= 0:
                continue
            fields = {k: v for k, v in q.items() if k in ADMIN_FIELDS}
            if not fields:
                continue
            sets = ', '.join(f'{k}=?' for k in fields)
            conn.execute(f'UPDATE questions SET {sets} WHERE id=?',
                         list(fields.values()) + [int(qid)])
            updated_count += 1

        new_count = 0
        for q in new_questions:
            question_text = str(q.get('question', '') or '').strip()
            if not question_text:
                continue
            row = {
                'domain':      str(q.get('domain',      '') or 'General'),
                'question':    question_text,
                'opt_a':       str(q.get('opt_a',       '') or ''),
                'opt_b':       str(q.get('opt_b',       '') or ''),
                'opt_c':       str(q.get('opt_c',       '') or ''),
                'opt_d':       str(q.get('opt_d',       '') or ''),
                'correct_idx': str(q.get('correct_idx', '0')),
                'explanation': str(q.get('explanation', '') or ''),
            }
            if 'opt_e' in cols:
                row['opt_e'] = str(q.get('opt_e', '') or '')
                row['opt_f'] = str(q.get('opt_f', '') or '')
            if 'is_multi' in cols:
                row['is_multi']     = 1 if q.get('is_multi') else 0
                row['select_count'] = int(q.get('select_count') or 1)
            cols_str = ', '.join(row.keys())
            ph       = ', '.join('?' * len(row))
            try:
                conn.execute(f'INSERT INTO questions ({cols_str}) VALUES ({ph})',
                             list(row.values()))
                new_count += 1
            except _sqlite3.IntegrityError:
                pass  # question déjà présente (index unique)

        conn.commit()
        total = conn.execute('SELECT COUNT(*) FROM questions').fetchone()[0]
        conn.execute("INSERT OR REPLACE INTO meta VALUES ('question_count',?)", [str(total)])
        conn.commit()
        conn.close()
        _bump_exam_version(exam)
        return 200, {'ok': True, 'updated': updated_count, 'new': new_count, 'total': total}
    except Exception as e:
        return 500, {'error': str(e)}


def _admin_upload_exam(body):
    exam_id = str(body.get('id', '')).strip().lower()
    title   = str(body.get('title', '')).strip() or exam_id
    b64     = str(body.get('sqlite_b64', ''))
    if not exam_id or not b64:
        return 400, {'error': 'id et sqlite_b64 requis'}
    if not re.match(r'^[a-z0-9_-]{1,64}$', exam_id):
        return 400, {'error': 'ID invalide (a-z, 0-9, _, -)'}
    try:
        data = _base64.b64decode(b64)
    except Exception:
        return 400, {'error': 'Base64 invalide'}
    if not data.startswith(b'SQLite format 3\x00'):
        return 400, {'error': 'Fichier SQLite invalide'}
    os.makedirs('data/content', exist_ok=True)
    with open(f'data/content/{exam_id}.sqlite', 'wb') as f:
        f.write(data)
    # Create/update exams/<id>.json so it appears in the admin list
    exam_json = f'exams/{exam_id}.json'
    existing = {}
    if os.path.exists(exam_json):
        try:
            with open(exam_json, encoding='utf-8') as f:
                existing = json.load(f)
        except Exception:
            pass
    existing.update({'id': exam_id, 'title': title,
                     'contentFile': f'data/content/{exam_id}.sqlite'})
    existing.setdefault('version', 1)
    with open(exam_json, 'w', encoding='utf-8') as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    return 200, {'ok': True, 'id': exam_id}


def _db_cols(conn):
    """Return set of column names for the questions table."""
    rows = conn.execute("PRAGMA table_info(questions)").fetchall()
    return {r[1] for r in rows}


def _q_select(cols):
    """Build SELECT columns list adapted to the actual schema."""
    base = 'id,domain,question,opt_a,opt_b,opt_c,opt_d'
    ext  = ',COALESCE(opt_e,"") AS opt_e,COALESCE(opt_f,"") AS opt_f' if 'opt_e' in cols else ',"" AS opt_e,"" AS opt_f'
    multi = ',is_multi,select_count' if 'is_multi' in cols else ',0 AS is_multi,1 AS select_count'
    return base + ext + ',correct_idx,explanation' + multi


def _admin_get_questions(exam, search='', page=1, per_page=50):
    path = f'data/content/{exam}.sqlite'
    if not os.path.exists(path):
        return None, 'Examen introuvable'
    try:
        conn = _sqlite3.connect(path)
        conn.row_factory = _sqlite3.Row
        cols = _db_cols(conn)
        where, params = '', []
        if search:
            where  = 'WHERE (question LIKE ? OR domain LIKE ?)'
            params = [f'%{search}%', f'%{search}%']
        total  = conn.execute(f'SELECT COUNT(*) FROM questions {where}', params).fetchone()[0]
        offset = (page - 1) * per_page
        rows   = conn.execute(
            f'SELECT {_q_select(cols)} FROM questions {where} ORDER BY id LIMIT ? OFFSET ?',
            params + [per_page, offset]).fetchall()
        conn.close()
        return {'total': total, 'page': page, 'per_page': per_page,
                'questions': [dict(r) for r in rows]}, None
    except Exception as e:
        return None, str(e)


def _admin_get_question(exam, qid):
    path = f'data/content/{exam}.sqlite'
    if not os.path.exists(path):
        return None, 'Examen introuvable'
    try:
        conn = _sqlite3.connect(path)
        conn.row_factory = _sqlite3.Row
        cols = _db_cols(conn)
        row  = conn.execute(
            f'SELECT {_q_select(cols)} FROM questions WHERE id=?', [qid]).fetchone()
        conn.close()
        if not row:
            return None, 'Question introuvable'
        return dict(row), None
    except Exception as e:
        return None, str(e)


def _admin_update_question(exam, qid, fields):
    path = f'data/content/{exam}.sqlite'
    if not os.path.exists(path):
        return 'Examen introuvable'
    updates = {k: v for k, v in fields.items() if k in ADMIN_FIELDS}
    if not updates:
        return 'Aucun champ valide'
    try:
        conn  = _sqlite3.connect(path)
        sets  = ', '.join(f'{k}=?' for k in updates)
        vals  = list(updates.values()) + [qid]
        conn.execute(f'UPDATE questions SET {sets} WHERE id=?', vals)
        conn.commit()
        conn.close()
        _bump_exam_version(exam)
        return None
    except Exception as e:
        return str(e)


def _bump_exam_version(exam):
    path = f'exams/{exam}.json'
    try:
        with open(path, encoding='utf-8') as f:
            meta = json.load(f)
        meta['version'] = meta.get('version', 1) + 1
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def _admin_save_creds(salt, hash_):
    creds = {'salt': salt, 'hash': hash_, 'first_login': False}
    content = 'window.__ADMIN_CREDS = ' + json.dumps(creds) + ';\n'
    try:
        with open(ADMIN_CREDS_FILE, 'w', encoding='utf-8') as f:
            f.write(content)
        return None
    except Exception as e:
        return str(e)


def _clean_srt(text):
    text = re.sub(r'^\d+\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}', '', text)
    text = re.sub(r'<[^>]+>', '', text)
    lines = [l for l in text.splitlines() if l.strip()]
    return '\n'.join(lines).strip()


class ProxyHandler(http.server.SimpleHTTPRequestHandler):

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors_headers()
        self.end_headers()

    def do_GET(self):
        # Block admin credentials file
        if self.path == '/data/admin.js':
            self.send_error(403, 'Forbidden')
            return
        p = urlparse(self.path)
        if p.path == '/api/admin/salt':
            creds = _admin_load_creds()
            if not creds:
                self._json_response(503, {'error': 'Fichier admin.js introuvable'}); return
            self._json_response(200, {'salt': creds['salt'],
                                      'first_login': creds.get('first_login', False)}); return
        if p.path == '/api/admin/env':
            container = os.path.exists('/.dockerenv') or bool(os.environ.get('KUBERNETES_SERVICE_HOST'))
            self._json_response(200, {'container': container}); return
        if p.path.startswith('/api/admin/'):
            if not _admin_verify(self):
                self._json_response(401, {'error': 'Non autorisé'}); return
            qs = parse_qs(p.query)
            get = lambda k, d='': (qs.get(k, [d]) or [d])[0]
            if p.path == '/api/admin/exams':
                self._json_response(200, _admin_list_exams()); return
            if p.path == '/api/admin/questions':
                data, err = _admin_get_questions(
                    get('exam'), get('search'), int(get('page','1')), int(get('per_page','50')))
                if err: self._json_response(400, {'error': err}); return
                self._json_response(200, data); return
            if p.path == '/api/admin/question':
                data, err = _admin_get_question(get('exam'), int(get('id','0')))
                if err: self._json_response(404, {'error': err}); return
                self._json_response(200, data); return
            if p.path == '/api/admin/export':
                self._admin_export_sqlite(get('exam')); return
            self.send_error(404, 'Not found'); return
        super().do_GET()

    def _admin_export_sqlite(self, exam):
        path = f'data/content/{exam}.sqlite'
        if not os.path.exists(path):
            self._json_response(404, {'error': 'Examen introuvable'}); return
        with open(path, 'rb') as f:
            data = f.read()
        self.send_response(200)
        self._cors_headers()
        self.send_header('Content-Type', 'application/octet-stream')
        self.send_header('Content-Disposition', f'attachment; filename="{exam}.sqlite"')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if self.path == '/api/translate':
            self._proxy_to_anthropic()
        elif self.path == '/api/transcript':
            self._get_transcript()
        elif self.path == '/api/ollama':
            self._proxy_to_ollama()
        elif self.path == '/api/openai':
            self._proxy_to_openai_compat('https://api.openai.com/v1/chat/completions')
        elif self.path == '/api/mistral':
            self._proxy_to_openai_compat('https://api.mistral.ai/v1/chat/completions')
        elif self.path.startswith('/api/admin/'):
            self._admin_post()
        else:
            self.send_error(404, 'Not found')

    def _admin_post(self):
        if not _admin_verify(self):
            self._json_response(401, {'error': 'Non autorisé'}); return
        length = int(self.headers.get('Content-Length', 0))
        try:
            body = json.loads(self.rfile.read(length))
        except Exception:
            self._json_response(400, {'error': 'JSON invalide'}); return

        if self.path == '/api/admin/update-question':
            exam = body.get('exam', '')
            qid  = int(body.get('id', 0))
            fields = {k: v for k, v in body.items() if k in ADMIN_FIELDS}
            err = _admin_update_question(exam, qid, fields)
            if err: self._json_response(400, {'error': err}); return
            self._json_response(200, {'ok': True}); return

        if self.path == '/api/admin/change-password':
            salt = str(body.get('salt', ''))
            hash_ = str(body.get('hash', ''))
            if not salt or not hash_:
                self._json_response(400, {'error': 'salt et hash requis'}); return
            err = _admin_save_creds(salt, hash_)
            if err: self._json_response(500, {'error': err}); return
            self._json_response(200, {'ok': True}); return

        if self.path == '/api/admin/upload-exam':
            status, result = _admin_upload_exam(body)
            self._json_response(status, result); return

        if self.path == '/api/admin/apply-updates':
            exam     = str(body.get('exam', ''))
            updated  = body.get('updated', [])
            new_qs   = body.get('new', [])
            if not exam:
                self._json_response(400, {'error': 'exam requis'}); return
            status, result = _admin_apply_updates(exam, updated, new_qs)
            self._json_response(status, result); return

        self.send_error(404, 'Not found')

    def _proxy_to_anthropic(self):
        """Forwarder la requête vers l'API Anthropic et renvoyer la réponse."""
        length  = int(self.headers.get('Content-Length', 0))
        body    = self.rfile.read(length)
        api_key = self.headers.get('X-Api-Key', '')

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
        try:
            with urllib.request.urlopen(req, context=SSL_CTX, timeout=120) as resp:
                data   = resp.read()
                status = resp.status
        except urllib.error.HTTPError as e:
            data   = e.read()
            status = e.code
        except Exception as e:
            self.send_error(502, str(e))
            return

        self.send_response(status)
        self._cors_headers()
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json_response(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self._cors_headers()
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _get_transcript(self):
        """Télécharge les sous-titres via l'API Python yt-dlp."""
        length = int(self.headers.get('Content-Length', 0))
        try:
            body = json.loads(self.rfile.read(length))
        except Exception:
            self._json_response(400, {'error': 'JSON invalide'}); return

        url  = body.get('url', '').strip()
        lang = (body.get('lang', 'en') or 'en').strip()
        if not url:
            self._json_response(400, {'error': 'URL manquante'}); return

        if not _YTDLP_OK:
            self._json_response(503, {
                'error': 'yt-dlp introuvable — lancez : pip install yt-dlp'
            }); return

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                with _yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True,
                                         'extract_flat': True,
                                         'source_address': '0.0.0.0'}) as ydl:
                    info = ydl.extract_info(url, download=False)

                if 'entries' in info:
                    videos = [{'id': e['id'], 'title': e.get('title', e['id'])}
                              for e in (info['entries'] or []) if e and e.get('id')]
                else:
                    videos = [{'id': info['id'], 'title': info.get('title', info['id'])}]

                if not videos:
                    self._json_response(422, {
                        'error': 'Impossible de lister les vidéos. Vérifiez l\'URL.'
                    }); return

                # lang.* (glob) matche fr-FR, fr-BE, en-orig, etc.
                sub_langs = [lang + '.*']
                transcripts = []
                for i, video in enumerate(videos):
                    if i > 0:
                        time.sleep(2)   # évite le 429 sur les playlists
                    ydl_opts = {
                        'quiet': True, 'no_warnings': True,
                        'skip_download': True,
                        'writesubtitles': True,
                        'writeautomaticsub': True,
                        'subtitleslangs': sub_langs,
                        'subtitlesformat': 'srt',
                        'outtmpl': os.path.join(tmpdir, video['id'] + '.%(ext)s'),
                        'retries': 5,
                        'sleep_interval': 2,
                        'sleep_interval_requests': 1,
                        'source_address': '0.0.0.0',
                    }
                    with _yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download(['https://youtu.be/' + video['id']])

                    matches = glob.glob(os.path.join(tmpdir, video['id'] + '*.srt'))
                    if matches:
                        with open(matches[0], encoding='utf-8', errors='ignore') as f:
                            raw = f.read()
                        txt = _clean_srt(raw)
                        if txt:
                            transcripts.append({'title': video['title'], 'text': txt})

                if not transcripts:
                    self._json_response(422, {
                        'error': f'Aucun sous-titre "{lang}" trouvé. Essayez l\'autre langue dans le sélecteur.'
                    }); return

                self._json_response(200, {'transcripts': transcripts})

        except Exception as e:
            err = str(e)
            if '429' in err:
                self._json_response(429, {
                    'error': 'YouTube limite les requêtes (429 Too Many Requests). Attendez 1-2 minutes puis réessayez.'
                })
            else:
                self._json_response(500, {'error': err})

    def _proxy_to_openai_compat(self, api_url):
        """Proxy générique pour les APIs OpenAI-compatibles (OpenAI, Mistral).
        Reçoit un body au format Anthropic-like, convertit, normalise la réponse."""
        length  = int(self.headers.get('Content-Length', 0))
        api_key = self.headers.get('X-Api-Key', '')
        try:
            body = json.loads(self.rfile.read(length))
        except Exception:
            self._json_response(400, {'error': 'JSON invalide'}); return

        model      = body.get('model', '')
        max_tokens = body.get('max_tokens', 4096)
        system     = body.get('system', '')
        messages   = body.get('messages', [])

        # Conversion : le champ "system" devient un message role:system en tête
        openai_messages = []
        if system:
            openai_messages.append({'role': 'system', 'content': system})
        openai_messages.extend(messages)

        payload = json.dumps({
            'model':      model,
            'max_tokens': max_tokens,
            'messages':   openai_messages,
        }).encode()

        req = urllib.request.Request(
            api_url,
            data=payload,
            headers={
                'Content-Type':  'application/json',
                'Authorization': 'Bearer ' + api_key,
            },
            method='POST'
        )
        try:
            with urllib.request.urlopen(req, context=SSL_CTX, timeout=120) as resp:
                data = json.loads(resp.read())
            text = data.get('choices', [{}])[0].get('message', {}).get('content', '')
            self._json_response(200, {'content': [{'text': text}]})
        except urllib.error.HTTPError as e:
            raw = e.read() or b'{}'
            try:
                err_body = json.loads(raw)
                msg = err_body.get('error', {}).get('message', '') or str(err_body)
            except Exception:
                msg = raw.decode(errors='replace')
            self._json_response(e.code, {'error': msg})
        except Exception as e:
            self._json_response(502, {'error': str(e)})

    def _proxy_to_ollama(self):
        """Proxifie une requête vers une instance Ollama locale."""
        length = int(self.headers.get('Content-Length', 0))
        try:
            body = json.loads(self.rfile.read(length))
        except Exception:
            self._json_response(400, {'error': 'JSON invalide'}); return

        ollama_url   = body.get('ollama_url', 'http://localhost:11434').rstrip('/')
        model        = body.get('model', 'llama3.2')
        system_msg   = body.get('system', '')
        messages     = body.get('messages', [])

        payload = json.dumps({
            'model':    model,
            'messages': [{'role': 'system', 'content': system_msg}] + messages,
            'stream':   False
        }).encode()

        try:
            req = urllib.request.Request(
                ollama_url + '/api/chat',
                data=payload,
                headers={'Content-Type': 'application/json'},
                method='POST'
            )
            ctx = SSL_CTX if ollama_url.startswith('https') else None
            with urllib.request.urlopen(req, context=ctx, timeout=300) as resp:
                data = json.loads(resp.read())
            text = data.get('message', {}).get('content', '')
            self._json_response(200, {'content': [{'text': text}]})
        except urllib.error.URLError as e:
            self._json_response(502, {'error': 'Ollama inaccessible : ' + str(e.reason)})
        except Exception as e:
            self._json_response(500, {'error': str(e)})

    def end_headers(self):
        # Ne pas cacher les ressources dynamiques ni le HTML en mode dev
        if self.path.endswith(('.html', '.json', '.sqlite', '.db')):
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        super().end_headers()

    def _cors_headers(self):
        self.send_header('Access-Control-Allow-Origin',  CORS_ORIGIN)
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers',
                         'Content-Type, X-Api-Key, anthropic-version, Authorization')

    def log_message(self, fmt, *args):
        msg  = fmt % args
        code = args[1] if len(args) > 1 else ''
        color = '\033[32m' if code.startswith('2') else \
                '\033[33m' if code.startswith('3') else \
                '\033[31m' if code and code[0] in '45' else ''
        print(f"\033[90m[{self.address_string()}]\033[0m {color}{msg}\033[0m")


def main():
    # Servir le répertoire PARENT de ./bin (la racine du projet)
    bin_dir  = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(bin_dir)
    os.chdir(root_dir)

    server = http.server.HTTPServer((HOST, PORT), ProxyHandler)
    print(f"\n\033[1;32m✓ Exam Prep server démarré\033[0m")
    print(f"  Fichiers    : http://{HOST}:{PORT}/")
    print(f"  Proxy API   : http://{HOST}:{PORT}/api/translate")
    print(f"  Racine      : {root_dir}")
    print(f"\n  Ouvrir      : \033[1;34mhttp://{HOST}:{PORT}/Exam-Prep.html\033[0m")
    print(f"\n  Arrêt       : Ctrl+C\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n\033[33m↩ Serveur arrêté\033[0m")


if __name__ == '__main__':
    main()
