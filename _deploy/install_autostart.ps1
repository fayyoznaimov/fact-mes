<#
    Автозапуск приложения цеха на сервере.

    Регистрирует задание планировщика Windows: приложение стартует при включении
    сервера, само поднимается после падения и работает без вошедшего пользователя.
    Отдельная служба (nssm) для этого не нужна.

        powershell -ExecutionPolicy Bypass -File install_autostart.ps1
        powershell -ExecutionPolicy Bypass -File install_autostart.ps1 -Fact http://172.0.30.9

    Посмотреть состояние:  Get-ScheduledTask "Цех — приложение"
    Остановить:            Stop-ScheduledTask "Цех — приложение"
    Снять с автозапуска:   Unregister-ScheduledTask "Цех — приложение"
#>
param(
    [string]$Fact = "",
    [int]$Port = 8780,
    [string]$TaskName = "Цех — приложение"
)

$ErrorActionPreference = "Stop"

$app = Join-Path (Split-Path -Parent $PSScriptRoot) "_app"
if (-not (Test-Path (Join-Path $app "app.py"))) {
    throw "Не нашёл приложение: $app\app.py"
}

$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) { throw "Python не найден в PATH — установите Python 3.10 или новее" }

# Настройки запуска держим в config.json, чтобы адрес FACT правился в файле,
# а не в задании планировщика. Существующий файл дополняем, а не переписываем:
# иначе повторная установка сотрёт настройки телеграма.
$cfgPath = Join-Path $app "config.json"
$cfg = @{}
if (Test-Path $cfgPath) {
    (Get-Content $cfgPath -Raw -Encoding UTF8 | ConvertFrom-Json).PSObject.Properties |
        ForEach-Object { $cfg[$_.Name] = $_.Value }
}
$cfg["port"] = $Port
if ($Fact) { $cfg["fact"] = $Fact }
$cfg | ConvertTo-Json -Depth 5 | Set-Content -Path $cfgPath -Encoding utf8
Write-Host "Настройки записаны: $cfgPath"

$action = New-ScheduledTaskAction -Execute $python -Argument "app.py" -WorkingDirectory $app
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -RunLevel Highest

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal -Description "Отчёты цеха и тикеты простоев" | Out-Null
Start-ScheduledTask -TaskName $TaskName

Start-Sleep -Seconds 5
try {
    $h = Invoke-RestMethod "http://127.0.0.1:$Port/api/health" -TimeoutSec 10
    Write-Host "Приложение отвечает. Проверки:" -ForegroundColor Green
    $h.checks.PSObject.Properties | ForEach-Object { Write-Host ("  {0}: {1}" -f $_.Name, $_.Value) }
} catch {
    Write-Warning "Приложение пока не отвечает: $($_.Exception.Message)"
    Write-Host "Смотрите журнал: $app\logs\app.log"
}

Write-Host ""
Write-Host "Приложение:        http://$(hostname):$Port"
Write-Host "Доска мониторов:   http://$(hostname):$Port/wall?zone=D"
