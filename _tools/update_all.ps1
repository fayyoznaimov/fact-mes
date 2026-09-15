# Ежедневное обновление: забрать свежие данные и пересобрать отчёты и дашборды.
#
#   powershell -ExecutionPolicy Bypass -File update_all.ps1              # всё целиком
#   powershell -ExecutionPolicy Bypass -File update_all.ps1 -Offline     # без обращения к серверу
#   powershell -ExecutionPolicy Bypass -File update_all.ps1 -Report 2026.09.12   # ещё и Excel за день
#
param(
  [switch]$Offline,              # работать только по локальному зеркалу
  [string]$Report,               # дата для выгрузки Excel-отчёта, например 2026.09.12
  [string]$Working,              # дата для листа Working по ТЗ
  [string]$TechCards,            # файл или адрес API 1С с техкартами
  [string]$Fact = "http://172.0.30.9"
)

$ErrorActionPreference = "Stop"
$tools = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $tools
$env:PYTHONIOENCODING = "utf-8"

function Step([string]$title, [scriptblock]$body) {
  Write-Output ""
  Write-Output "== $title"
  $t0 = Get-Date
  & $body
  Write-Output ("   готово за {0:n0} с" -f ((Get-Date) - $t0).TotalSeconds)
}

if (-not $Offline) {
  $reachable = $false
  try {
    Invoke-WebRequest "$Fact/factdata/collect_date.txt" -UseBasicParsing -TimeoutSec 8 | Out-Null
    $reachable = $true
  } catch {
    Write-Output "Сервер FACT недоступен ($Fact) — работаю по зеркалу."
  }
  if ($reachable) {
    Step "Зеркалирование данных FACT" { python fact_mirror.py --fact $Fact }
  }
}

Step "Пересборка базы смен из зеркала" { python rebuild_db.py }
Step "Заливка отчётов по дням в базу"  { python backfill_reports.py }
Step "Дашборд: производственный отчёт" { python build_daily_view.py }
Step "Дашборд: разбор простоев"        { python build_explorer.py }
Step "Дашборд: обход цеха по сменам"   { python build_shift_view.py }

if ($TechCards) {
  Step "Техкарты из 1С" {
    if ($TechCards -match '^https?://') { python tech_cards.py --url $TechCards }
    else { python tech_cards.py --file $TechCards }
  }
}

if ($Report) {
  Step "Excel-отчёт за $Report" {
    python make_excel_report.py $Report
    powershell -ExecutionPolicy Bypass -File (Join-Path $tools "fill_template.ps1") -Day $Report
  }
}

if ($Working) {
  Step "Лист Working по ТЗ за $Working" { python build_working_report.py $Working }
}

Write-Output ""
Write-Output "Всё обновлено. Страницы лежат рядом:"
Get-ChildItem $tools -Filter *.html | ForEach-Object { "   {0,-26} {1,7:n0} КБ" -f $_.Name, ($_.Length / 1KB) }
