# Backend-тесты через .venv. DATABASE_URL/REDIS_URL должны быть ПУСТЫМИ, а не отсутствовать:
# локальный .env — docker-шаблон с хостами db/redis, а core/settings.py подгружает его через
# load_dotenv(override=False) и подставит значения, если переменной в окружении нет.
# `$env:X = ''` в PowerShell удаляет переменную, поэтому запускаем через ProcessStartInfo,
# где пустое значение остаётся в окружении дочернего процесса.
$root = Resolve-Path (Join-Path $PSScriptRoot '..')
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    Write-Error "Не найден .venv ($python). Создайте: python -m venv .venv; .venv\Scripts\pip install -r requirements.txt"
    exit 1
}

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $python
$psi.WorkingDirectory = $root.Path
$psi.UseShellExecute = $false
$psi.EnvironmentVariables['DATABASE_URL'] = ''
$psi.EnvironmentVariables['REDIS_URL'] = ''
$parts = @('manage.py', 'test') + $args
$psi.Arguments = ($parts | ForEach-Object { if ($_ -match '[\s"]') { '"' + ($_ -replace '"', '\"') + '"' } else { $_ } }) -join ' '

$proc = [System.Diagnostics.Process]::Start($psi)
$proc.WaitForExit()
exit $proc.ExitCode
