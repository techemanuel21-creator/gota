# Gota Desktop - updater: downloads the latest code from GitHub and refreshes the libraries. Keeps models, environment and your data.
#   irm https://raw.githubusercontent.com/techemanuel21-creator/gota/main/desktop/update.ps1 | iex
$env:GOTA_UPDATE = '1'
try {
    Invoke-Expression (Invoke-RestMethod 'https://raw.githubusercontent.com/techemanuel21-creator/gota/main/desktop/install.ps1')
} finally {
    Remove-Item Env:\GOTA_UPDATE -ErrorAction SilentlyContinue
}
