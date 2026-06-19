param(
    [Parameter(Mandatory)]
    [string]$PlaylistUrl,

    [string]$OutputDir = ".\transcripts",
    [string]$Lang = "en"
)

function Convert-SrtToText {
    param([string]$Path)
    $text = Get-Content $Path -Raw -Encoding UTF8
    # Supprimer numéros de séquence, horodatages et balises HTML
    $text = $text -replace '(?m)^\d+\r?\n', ''
    $text = $text -replace '\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}\r?\n?', ''
    $text = $text -replace '<[^>]+>', ''
    # Fusionner les lignes vides multiples en une seule ligne vide
    $lines = ($text -split '\r?\n') | Where-Object { $_.Trim() -ne '' }
    return ($lines -join "`n").Trim()
}

Write-Host "Extraction de la playlist..." -ForegroundColor Cyan
$lines = yt-dlp --flat-playlist --print "%(playlist_index)s. %(title)s [%(id)s]" $PlaylistUrl

if (-not $lines) {
    Write-Error "Aucune vidéo trouvée ou erreur yt-dlp."
    exit 1
}

$videos = foreach ($line in $lines) {
    if ($line -match '^(\d+\..+)\[([A-Za-z0-9_-]+)\]$') {
        [PSCustomObject]@{
            Title = $Matches[1].Trim()
            Id    = $Matches[2]
        }
    }
}

Write-Host "$($videos.Count) vidéos trouvées.`n" -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$ok = 0; $errCount = 0

foreach ($video in $videos) {
    Write-Host "[$($video.Title)]" -ForegroundColor Cyan

    yt-dlp `
        --cookies-from-browser chrome `
        --skip-download `
        --write-auto-sub `
        --sub-lang $Lang `
        --convert-subs srt `
        --output "$OutputDir\$($video.Title) [%(id)s].%(ext)s" `
        "https://youtu.be/$($video.Id)"

    if ($LASTEXITCODE -eq 0) {
        # Cherche le .srt téléchargé et le convertit en .txt lisible
        $srtFile = Get-ChildItem -Path $OutputDir -Filter "*$($video.Id)*.srt" | Select-Object -First 1
        if ($srtFile) {
            $txt = Convert-SrtToText $srtFile.FullName
            $txtPath = [System.IO.Path]::ChangeExtension($srtFile.FullName, '.txt')
            [System.IO.File]::WriteAllText($txtPath, $txt, [System.Text.Encoding]::UTF8)
            Write-Host "  OK — $($srtFile.Name) + .txt" -ForegroundColor Green
        } else {
            Write-Host "  OK (aucun sous-titre disponible pour cette vidéo)" -ForegroundColor Yellow
        }
        $ok++
    } else {
        Write-Warning "  ERREUR pour $($video.Id)"
        $errCount++
    }
}

Write-Host "`nTerminé : $ok OK, $errCount erreur(s)." -ForegroundColor Yellow
Write-Host "Fichiers dans : $OutputDir" -ForegroundColor Yellow
Write-Host "`nÉtape suivante :" -ForegroundColor Cyan
Write-Host "  python bin/transcript2questions.py ``" -ForegroundColor White
Write-Host "    --input $OutputDir ``" -ForegroundColor White
Write-Host "    --output data/content/monexamen.sqlite ``" -ForegroundColor White
Write-Host "    --exam-id monexamen ``" -ForegroundColor White
Write-Host "    --api-key `$env:ANTHROPIC_API_KEY" -ForegroundColor White
