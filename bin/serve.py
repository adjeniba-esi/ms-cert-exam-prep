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

PORT = 8080
HOST = '127.0.0.1'
if '--port' in sys.argv:
    PORT = int(sys.argv[sys.argv.index('--port') + 1])
if '--host' in sys.argv:
    HOST = sys.argv[sys.argv.index('--host') + 1]

ANTHROPIC_URL = 'https://api.anthropic.com/v1/messages'
SSL_CTX = ssl.create_default_context()


class ProxyHandler(http.server.SimpleHTTPRequestHandler):

    def do_OPTIONS(self):
        """Répondre aux preflight CORS."""
        self.send_response(200)
        self._cors_headers()
        self.end_headers()

    def do_POST(self):
        if self.path == '/api/translate':
            self._proxy_to_anthropic()
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
