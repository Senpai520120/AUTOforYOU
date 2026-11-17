# e2e-run.ps1 - запуск scripts/e2e-run.sh из PowerShell (задача 9.58).
# Вся логика в e2e-run.sh (один источник): сверка .env.e2e, остановка dev-стека без -v, подъём e2e-стека, FLUSHALL,
# e2e_seed, Playwright с вашими аргументами, затем всегда e2e-cleanup и возврат dev-стека. Код возврата = код Playwright.
# Нужен Git Bash (bash.exe из Git for Windows).
# Примеры: scripts\e2e-run.ps1 e2e/lead.spec.ts --project=chromium    scripts\e2e-run.ps1 --grep @smoke
$root = Resolve-Path (Join-Path $PSScriptRoot '..')
$bash = $null
foreach ($candidate in @("$env:ProgramFiles\Git\bin\bash.exe", "${env:ProgramFiles(x86)}\Git\bin\bash.exe", "$env:LOCALAPPDATA\Programs\Git\bin\bash.exe")) {
    if ($candidate -and (Test-Path $candidate)) { $bash = $candidate; break }
}
if (-not $bash) {
    $found = Get-Command bash.exe -ErrorAction SilentlyContinue
    if ($found -and $found.Source -notmatch 'System32') { $bash = $found.Source }
}
if (-not $bash) {
    Write-Error 'Не найден Git Bash (bash.exe). Установите Git for Windows или запустите ./scripts/e2e-run.sh из Git Bash.'
    exit 1
}
Push-Location $root
try {
    & $bash 'scripts/e2e-run.sh' @args
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
