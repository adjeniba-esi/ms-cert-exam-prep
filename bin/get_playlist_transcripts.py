#!/usr/bin/env python3
"""
get_playlist_transcripts.py
===========================
Télécharge les sous-titres de toutes les vidéos d'une playlist YouTube
via yt-dlp, puis convertit chaque .srt en .txt nettoyé (sans timestamps).

Prérequis : yt-dlp installé et accessible dans le PATH.

Usage :
    python bin/get_playlist_transcripts.py <playlist_url> [options]

Exemples :
    python bin/get_playlist_transcripts.py "https://youtube.com/playlist?list=..." --lang fr
    python bin/get_playlist_transcripts.py "https://youtube.com/playlist?list=..." --output transcripts/az104
"""
import argparse, glob, os, re, subprocess, sys

# ── Couleurs ANSI (désactivées si stdout n'est pas un terminal) ───────────────
def _color(code):
    return (lambda s: f'\033[{code}m{s}\033[0m') if sys.stdout.isatty() else (lambda s: s)

cyan   = _color('36')
yellow = _color('33')
green  = _color('32')
red    = _color('31')
dim    = _color('2')


def clean_srt(text):
    """Retire les numéros de séquence, horodatages et balises HTML d'un fichier SRT."""
    text = re.sub(r'^\d+\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}', '', text)
    text = re.sub(r'<[^>]+>', '', text)
    lines = [l for l in text.splitlines() if l.strip()]
    return '\n'.join(lines).strip()


def list_playlist(url):
    """Retourne la liste des vidéos : [{'title': ..., 'id': ...}, ...]"""
    result = subprocess.run(
        ['yt-dlp', '--flat-playlist', '--print', '%(playlist_index)s. %(title)s [%(id)s]', url],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(red(f'Erreur yt-dlp :\n{result.stderr.strip()}'), file=sys.stderr)
        sys.exit(1)

    videos = []
    for line in result.stdout.splitlines():
        m = re.match(r'^(\d+\..+)\[([A-Za-z0-9_-]+)\]$', line.strip())
        if m:
            videos.append({'title': m.group(1).strip(), 'id': m.group(2)})
    return videos


def download_subs(video, output_dir, lang):
    """Télécharge les sous-titres d'une vidéo en .srt. Retourne True si succès."""
    template = os.path.join(output_dir, f"{video['title']} [%(id)s].%(ext)s")
    result = subprocess.run(
        [
            'yt-dlp',
            '--cookies-from-browser', 'chrome',
            '--skip-download',
            '--write-auto-sub',
            '--sub-lang', lang,
            '--convert-subs', 'srt',
            '--output', template,
            f"https://youtu.be/{video['id']}",
        ],
        capture_output=True, text=True
    )
    return result.returncode == 0


def srt_to_txt(output_dir, video_id):
    """Cherche le .srt correspondant à video_id, le nettoie et écrit un .txt. Retourne le nom du fichier ou None."""
    pattern = os.path.join(output_dir, f'*{video_id}*.srt')
    matches = glob.glob(pattern)
    if not matches:
        return None

    srt_path = matches[0]
    with open(srt_path, encoding='utf-8', errors='ignore') as f:
        raw = f.read()

    txt = clean_srt(raw)
    txt_path = os.path.splitext(srt_path)[0] + '.txt'
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write(txt)

    return os.path.basename(srt_path)


def main():
    ap = argparse.ArgumentParser(
        description='Télécharge les sous-titres d\'une playlist YouTube et les convertit en .txt',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    ap.add_argument('playlist_url', help='URL de la playlist YouTube')
    ap.add_argument('--output', default='transcripts', metavar='DIR',
                    help='Dossier de sortie (défaut : transcripts)')
    ap.add_argument('--lang', default='en', metavar='LANG',
                    help='Code langue des sous-titres, ex. fr, en (défaut : en)')
    args = ap.parse_args()

    print(cyan('Extraction de la playlist...'))
    videos = list_playlist(args.playlist_url)

    if not videos:
        print(red('Aucune vidéo trouvée dans la playlist.'), file=sys.stderr)
        sys.exit(1)

    print(yellow(f'{len(videos)} vidéo(s) trouvée(s).\n'))
    os.makedirs(args.output, exist_ok=True)

    ok = err = 0

    for video in videos:
        print(cyan(f"[{video['title']}]"))
        success = download_subs(video, args.output, args.lang)

        if success:
            fname = srt_to_txt(args.output, video['id'])
            if fname:
                print(green(f"  OK — {fname} + .txt"))
            else:
                print(yellow('  OK (aucun sous-titre disponible pour cette vidéo)'))
            ok += 1
        else:
            print(red(f"  ERREUR pour {video['id']}"), file=sys.stderr)
            err += 1

    print(yellow(f'\nTerminé : {ok} OK, {err} erreur(s).'))
    print(yellow(f'Fichiers dans : {args.output}'))
    print(cyan('\nÉtape suivante :'))
    print(f'  python bin/transcript2questions.py \\')
    print(f'    --input {args.output} \\')
    print(f'    --output data/content/monexamen.sqlite \\')
    print(f'    --exam-id monexamen \\')
    print(f'    --api-key $ANTHROPIC_API_KEY')


if __name__ == '__main__':
    main()
