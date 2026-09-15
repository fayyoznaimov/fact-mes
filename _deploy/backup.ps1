<#
    Резервная копия цеховой базы.

    Копируется shop.db — то, что вводят люди: тикеты, пользователи, операторы,
    назначения на смену, ставка. Эти данные восстановить неоткуда. База станков
    fact.db не копируется: она пересобирается из зеркала командой rebuild_db.py.

    Копия снимается через VACUUM INTO — это безопасно на работающем приложении,
    в отличие от простого копирования файла.

        powershell -ExecutionPolicy Bypass -File backup.ps1 -To \\server\backup\ceh
        powershell -ExecutionPolicy Bypass -File backup.ps1 -To D:\backup -KeepDays 60
        powershell -ExecutionPolicy Bypass -File backup.ps1 -To D:\backup -Schedule   # ежедневно в 03:30
#>
param(
    [Parameter(Mandatory = $true)][string]$To,
    [int]$KeepDays = 30,
    [switch]$Schedule
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$shop = Join-Path $root "_app\shop.db"
if (-not (Test-Path $shop)) { throw "Не нашёл базу: $shop" }
if (-not (Test-Path $To)) { New-Item -ItemType Directory -Path $To -Force | Out-Null }

if ($Schedule) {
    $me = $MyInvocation.MyCommand.Path
    $action = New-ScheduledTaskAction -Execute "powershell" `
        -Argument "-ExecutionPolicy Bypass -File `"$me`" -To `"$To`" -KeepDays $KeepDays"
    $trigger = New-ScheduledTaskTrigger -Daily -At 3:30am
    $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -RunLevel Highest
    if (Get-ScheduledTask -TaskName "Цех — резервная копия" -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName "Цех — резервная копия" -Confirm:$false
    }
    Register-ScheduledTask -TaskName "Цех — резервная копия" -Action $action -Trigger $trigger `
        -Principal $principal -Description "Копия базы цеха в $To" | Out-Null
    Write-Host "Копия будет сниматься каждый день в 03:30 в $To"
    return
}

$stamp = Get-Date -Format "yyyy-MM-dd_HHmm"
$dest = Join-Path $To "shop_$stamp.db"
$py = @"
import sqlite3, sys
src, dst = sys.argv[1], sys.argv[2]
c = sqlite3.connect(src)
c.execute('VACUUM INTO ?', (dst,))
c.close()
"@
$tmp = Join-Path $env:TEMP "shop_backup.py"
Set-Content -Path $tmp -Value $py -Encoding utf8
python $tmp $shop $dest
if (-not (Test-Path $dest)) { throw "Копия не создалась: $dest" }
Write-Host ("Копия: {0} ({1:N1} МБ)" -f $dest, ((Get-Item $dest).Length / 1MB))

$old = Get-ChildItem $To -Filter "shop_*.db" |
       Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$KeepDays) }
if ($old) {
    $old | Remove-Item -Force
    Write-Host "Удалено старых копий: $($old.Count) (старше $KeepDays дней)"
}
