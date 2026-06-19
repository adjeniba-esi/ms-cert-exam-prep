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
import json, re, subprocess, tempfile, glob

PORT = 8080
HOST = '127.0.0.1'
if '--port' in sys.argv:
    PORT = int(sys.argv[sys.argv.index('--port') + 1])
if '--host' in sys.argv:
    HOST = sys.argv[sys.argv.index('--host') + 1]

ANTHROPIC_URL = 'https://api.anthropic.com/v1/messages'
SSL_CTX = ssl.create_default_context()


def _clean_srt(text):
    text = re.sub(r'^\d+\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}', '', text)
    text = re.sub(r'<[^>]+>', '', text)
    lines = [l for l in text.splitlines() if l.strip()]
    return '\n'.join(lines).strip()


class ProxyHandler(http.server.SimpleHTTPRequestHandler):

    def do_OPTIONS(self):
        """Répondre aux preflight CORS."""
        self.send_response(200)
        self._cors_headers()
        self.end_headers()

    def do_POST(self):
        if self.path == '/api/translate':
            self._proxy_to_anthropic()
        elif self.path == '/api/transcript':
            self._get_transcript()
        elif self.path == '/api/ollama':
            self._proxy_to_ollama()
        else:
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
        """Télécharge les sous-titres via yt-dlp et retourne le texte nettoyé."""
        length = int(self.headers.get('Content-Length', 0))
        try:
            body = json.loads(self.rfile.read(length))
        except Exception:
            self._json_response(400, {'error': 'JSON invalide'}); return

        url  = body.get('url', '').strip()
        lang = (body.get('lang', 'en') or 'en').strip()
        if not url:
            self._json_response(400, {'error': 'URL manquante'}); return

        ytdlp_cmd = [sys.executable, '-m', 'yt_dlp']
        try:
            subprocess.run(ytdlp_cmd + ['--version'],
                           capture_output=True, check=True, timeout=10)
        except Exception:
            self._json_response(503, {
                'error': 'yt-dlp introuvable — lancez : pip install yt-dlp'
            }); return

        transcripts = []
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                # %(playlist_index)s vaut "NA" pour une vidéo unique → on utilise
                # un format sans index, séparé par TAB, valide pour vidéo et playlist
                r = subprocess.run(
                    ytdlp_cmd + ['--flat-playlist', '--print', '%(id)s\t%(title)s', url],
                    capture_output=True, text=True, timeout=60
                )
                videos = []
                for line in r.stdout.splitlines():
                    line = line.strip()
                    if '\t' in line:
                        vid_id, title = line.split('\t', 1)
                        vid_id = vid_id.strip()
                        if re.match(r'^[A-Za-z0-9_-]{6,20}$', vid_id):
                            videos.append({'title': title.strip(), 'id': vid_id})

                # Pattern lang.* pour matcher fr-FR, fr-BE, en-orig, etc.
                sub_lang = lang + '.*,' + lang
                for video in videos:
                    tpl = os.path.join(tmpdir, '%(id)s.%(ext)s')
                    subprocess.run(
                        ytdlp_cmd + ['--skip-download',
                         '--write-sub', '--write-auto-sub',
                         '--sub-lang', sub_lang,
                         '--convert-subs', 'srt',
                         '--output', tpl,
                         'https://youtu.be/' + video['id']],
                        capture_output=True, timeout=60
                    )
                    matches = glob.glob(
                        os.path.join(tmpdir, video['id'] + '*.srt'))
                    if matches:
                        with open(matches[0], encoding='utf-8', errors='ignore') as f:
                            raw = f.read()
                        txt = _clean_srt(raw)
                        if txt:
                            transcripts.append(
                                {'title': video['title'], 'text': txt})
        except Exception as e:
            self._json_response(500, {'error': str(e)}); return

        if not transcripts and not videos:
            self._json_response(200, {
                'error': f'Impossible de lister les vidéos. Vérifiez l\'URL.'
            }); return
        if not transcripts:
            self._json_response(200, {
                'error': f'Aucun sous-titre "{lang}" trouvé. Essayez l\'autre langue dans le sélecteur.'
            }); return
        self._json_response(200, {'transcripts': transcripts})

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
        self.send_header('Access-Control-Allow-Origin',  '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers',
                         'Content-Type, X-Api-Key, anthropic-version')

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
