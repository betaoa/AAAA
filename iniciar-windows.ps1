$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

if (Test-Path -LiteralPath '.env') {
    foreach ($linha in Get-Content -LiteralPath '.env') {
        if ($linha -match '^\s*([^#][^=]*)=(.*)$') {
            [Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), 'Process')
        }
    }
}

if (Test-Path -LiteralPath '.fontes') {
    $env:FONTES = (Get-Content -LiteralPath '.fontes' -Raw).Trim()
}

python videobot.py validar
python videobot.py daemon

