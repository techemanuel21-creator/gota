# Gota Desktop - installer / updater for Windows (run in PowerShell, no administrator needed)
#   install : irm https://raw.githubusercontent.com/techemanuel21-creator/gota/main/desktop/install.ps1 | iex
#   update  : irm https://raw.githubusercontent.com/techemanuel21-creator/gota/main/desktop/update.ps1  | iex
# Running it again is safe: it replaces the program files, keeps the Python environment and the AI models, and never touches your data (%APPDATA%\Gota).
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$repo = 'techemanuel21-creator/gota'
$branch = 'main'
$root = Join-Path $env:LOCALAPPDATA 'Gota-App'
$app = Join-Path $root 'desktop'
$update = [bool]$env:GOTA_UPDATE
Write-Host ("== Gota Desktop: " + $(if ($update) { 'atualizando' } else { 'instalando' }) + " em $root") -ForegroundColor Cyan

function Find-Python {
    foreach ($c in @(@('py', '-3.12'), @('python'))) {
        try {
            $exe = $c[0]; $extra = @($c | Select-Object -Skip 1)
            $v = & $exe @extra -c "import sys;print('%d.%d' % sys.version_info[:2])" 2>$null
            if ($LASTEXITCODE -eq 0 -and $v -eq '3.12') { return ,$c }
        } catch {}
    }
    return $null
}

# 1. Python 3.12 (needed by the AI libraries)
$py = Find-Python
if (-not $py) {
    Write-Host 'Python 3.12 nao encontrado. Instalando com o winget (so para o seu usuario)...' -ForegroundColor Yellow
    winget install --id Python.Python.3.12 -e --scope user --accept-source-agreements --accept-package-agreements
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'User') + ';' + [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $py = Find-Python
    if (-not $py) { throw 'Nao consegui instalar o Python 3.12. Instale em python.org e rode este comando de novo.' }
}

# 2. the program files: close Gota, REMOVE the old program completely, then put the freshly downloaded one.
#    Kept: models (several GB of AI), the Python environment, and your data in %APPDATA%\Gota (chats, WhatsApp/Outlook connections, settings).
Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Path -and $_.Path -like "$root*" } | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep 1
$tmp = Join-Path $env:TEMP ('gota_dl_' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force $tmp | Out-Null
try {
    Write-Host 'Baixando o codigo do GitHub...'
    $zip = Join-Path $tmp 'gota.zip'
    Invoke-WebRequest "https://github.com/$repo/archive/refs/heads/$branch.zip?t=$([DateTime]::UtcNow.Ticks)" -OutFile $zip -UseBasicParsing
    Expand-Archive $zip -DestinationPath $tmp -Force
    $src = Join-Path (Get-ChildItem $tmp -Directory | Select-Object -First 1).FullName 'desktop'
    if (-not (Test-Path (Join-Path $src 'main.py'))) { throw 'O download veio incompleto (main.py nao encontrado).' }
    New-Item -ItemType Directory -Force $app | Out-Null
    Get-ChildItem $app -Force | Where-Object { $_.Name -notin @('models', '.venv') } | Remove-Item -Recurse -Force
    robocopy $src $app /E /XD .venv models /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "Falha ao copiar os arquivos (robocopy $LASTEXITCODE)." }
} finally {
    Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
}
New-Item -ItemType Directory -Force (Join-Path $app 'models') | Out-Null
$version = 'desconhecida'
try {
    $c = Invoke-RestMethod "https://api.github.com/repos/$repo/commits/$branch" -Headers @{ 'User-Agent' = 'gota-installer' }
    $version = $c.sha.Substring(0, 7) + ' - ' + ($c.commit.message -split "`n")[0]
} catch {}
Set-Content (Join-Path $app 'VERSION.txt') $version -Encoding ASCII

# 3. Python environment + libraries (first time: several GB, takes a while; later only what changed)
$venvPy = Join-Path $app '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPy)) {
    Write-Host 'Criando o ambiente Python...'
    $exe = $py[0]; $extra = @($py | Select-Object -Skip 1)
    & $exe @extra -m venv (Join-Path $app '.venv')
}
Write-Host 'Instalando/atualizando as bibliotecas (pode demorar na primeira vez)...'
& $venvPy -m pip install --upgrade pip --quiet
& $venvPy -m pip install -r (Join-Path $app 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar as bibliotecas.' }

# 4. shortcut on the desktop and in the Start menu (recreated every time, so they always point to this copy)
if ($true) {
    $shell = New-Object -ComObject WScript.Shell
    $target = Join-Path $app '.venv\Scripts\pythonw.exe'
    foreach ($dir in @([Environment]::GetFolderPath('Desktop'), (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'))) {
        $lnk = $shell.CreateShortcut((Join-Path $dir 'Gota.lnk'))
        $lnk.TargetPath = $target
        $lnk.Arguments = 'main.py'
        $lnk.WorkingDirectory = $app
        $lnk.IconLocation = (Join-Path $app 'gota\assets\gota.ico')
        $lnk.Save()
    }
}

Write-Host ''
Write-Host "Versao instalada: $version" -ForegroundColor Green
Write-Host 'Pronto! Abra o Gota pelo atalho "Gota" na area de trabalho.' -ForegroundColor Green
Write-Host 'No primeiro uso ele baixa os modelos de IA (alguns GB) para a pasta models; precisa de internet e de espaco em disco.'
Write-Host 'Para atualizar depois: irm https://raw.githubusercontent.com/techemanuel21-creator/gota/main/desktop/update.ps1 | iex'
