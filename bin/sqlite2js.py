#!/usr/bin/env python3
"""
sqlite2js — Convertit les fichiers de données en modules .js chargeables en file://
===================================================================================
Les balises <script src> ne sont pas soumises à la politique CORS, contrairement
à fetch(). Ce script génère, à côté de chaque fichier de données, un .js qui
enregistre son contenu dans une variable globale. L'application peut alors être
ouverte par double-clic (file://) sans serveur HTTP.

Génère :
  ./exams/index.json            -> ./exams/index.js
  ./exams/<id>.json             -> ./exams/<id>.js
  ./data/content/<f>.sqlite     -> ./data/content/<f>.sqlite.js
  ./data/results/<f>.sqlite     -> ./data/results/<f>.sqlite.js

Usage :
    python bin/sqlite2js.py                 # convertit tout
    python bin/sqlite2js.py --watch         # reconvertit à chaque modification
    python bin/sqlite2js.py --clean         # supprime les .js générés
"""
import base64, json, os, sys, time, glob

BIN_DIR  = os.path.dirname(os.path.abspath(__file__))
ROOT     = os.path.dirname(BIN_DIR)
EXAMS    = os.path.join(ROOT, 'exams')
CONTENT  = os.path.join(ROOT, 'data', 'content')
RESULTS  = os.path.join(ROOT, 'data', 'results')


def _write(path, text):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


def convert_index():
    """exams/index.json -> exams/index.js"""
    src = os.path.join(EXAMS, 'index.json')
    if not os.path.exists(src):
        return 0
    with open(src, encoding='utf-8') as f:
        data = json.load(f)
    ids = data.get('exams', [])
    js = 'window.__EXAM_INDEX = ' + json.dumps(ids, ensure_ascii=False) + ';\n'
    _write(os.path.join(EXAMS, 'index.js'), js)
    print(f"  exams/index.json -> exams/index.js  ({len(ids)} examens)")
    return 1


def convert_exam_configs():
    """exams/<id>.json -> exams/<id>.js"""
    n = 0
    for src in sorted(glob.glob(os.path.join(EXAMS, '*.json'))):
        name = os.path.basename(src)
        if name == 'index.json':
            continue
        with open(src, encoding='utf-8') as f:
            cfg = json.load(f)
        qid = cfg.get('id') or os.path.splitext(name)[0]
        js = ('(window.__EXAM_CONFIGS=window.__EXAM_CONFIGS||{})['
              + json.dumps(qid) + ']=' + json.dumps(cfg, ensure_ascii=False) + ';\n')
        out = os.path.splitext(src)[0] + '.js'
        _write(out, js)
        print(f"  {os.path.relpath(src, ROOT)} -> {os.path.relpath(out, ROOT)}")
        n += 1
    return n


def convert_sqlite_dir(directory, global_var, label):
    """data/.../<f>.sqlite -> data/.../<f>.sqlite.js"""
    n = 0
    if not os.path.isdir(directory):
        return 0
    for src in sorted(glob.glob(os.path.join(directory, '*.sqlite'))
                      + glob.glob(os.path.join(directory, '*.db'))):
        with open(src, 'rb') as f:
            data = f.read()
        b64 = base64.b64encode(data).decode('ascii')
        key = os.path.basename(src)
        js = ('(window.' + global_var + '=window.' + global_var + '||{})['
              + json.dumps(key) + ']=' + json.dumps(b64) + ';\n')
        out = src + '.js'
        _write(out, js)
        print(f"  {os.path.relpath(src, ROOT)} -> {os.path.relpath(out, ROOT)}"
              f"  ({len(data)//1024} KB -> {len(b64)//1024} KB b64)")
        n += 1
    return n


def convert_all():
    print("Conversion SQLite/JSON -> JS …")
    c = 0
    c += convert_index()
    c += convert_exam_configs()
    c += convert_sqlite_dir(CONTENT, '__EXAM_CONTENT', 'content')
    c += convert_sqlite_dir(RESULTS, '__EXAM_RESULTS', 'results')
    print(f"OK — {c} fichier(s) généré(s).")
    return c


def clean():
    print("Suppression des .js générés …")
    n = 0
    for pat in [os.path.join(EXAMS, '*.js'),
                os.path.join(CONTENT, '*.js'),
                os.path.join(RESULTS, '*.js')]:
        for f in glob.glob(pat):
            os.remove(f); n += 1
            print(f"  supprimé {os.path.relpath(f, ROOT)}")
    print(f"OK — {n} fichier(s) supprimé(s).")


def watch():
    print("Surveillance des modifications (Ctrl+C pour arrêter)…")
    mtimes = {}
    dirs = [EXAMS, CONTENT, RESULTS]
    try:
        while True:
            changed = False
            for d in dirs:
                for f in glob.glob(os.path.join(d, '*.sqlite')) + \
                         glob.glob(os.path.join(d, '*.db')) + \
                         glob.glob(os.path.join(d, '*.json')):
                    m = os.path.getmtime(f)
                    if mtimes.get(f) != m:
                        mtimes[f] = m
                        changed = True
            if changed:
                convert_all()
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nArrêt.")


if __name__ == '__main__':
    if '--clean' in sys.argv:
        clean()
    elif '--watch' in sys.argv:
        convert_all()
        watch()
    else:
        convert_all()
