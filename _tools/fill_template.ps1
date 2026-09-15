# Заполняет ваш шаблон производственного отчёта данными из FACT.
# Оригинальный файл не изменяется — работа идёт с копией.
#
#   powershell -File fill_template.ps1 -Day 2026.09.11
#
param(
  [Parameter(Mandatory = $true)][string]$Day,
  [string]$Template = "C:\Users\Asus\Downloads\Telegram Desktop\11.09,2026New oduction Report (5) 211.xlsb",
  [string]$OutDir,
  [string]$RowsCsv
)

$tools = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $OutDir) { $OutDir = Join-Path (Split-Path -Parent $tools) "reports" }
if (-not $RowsCsv) { $RowsCsv = Join-Path $tools "_rows_$Day.csv" }
if (-not (Test-Path $RowsCsv)) { throw "Нет файла с данными: $RowsCsv (сначала запустите make_excel_report.py $Day)" }
if (-not (Test-Path $Template)) { throw "Не найден шаблон: $Template" }
New-Item -ItemType Directory -Force $OutDir | Out-Null

# --- читаем данные ---
$lines = [IO.File]::ReadAllLines($RowsCsv, [Text.UTF8Encoding]::new($true)) | Where-Object { $_.Trim() }
$data = @($lines | ForEach-Object { , ($_ -split ';') })
if (-not $data.Count) { throw "Файл данных пуст" }

$FIRST_ROW = 6                       # строки станков в листе TOYOTA начинаются с 6-й
$COLS = 37                           # колонки A..AK
$LAST_ROW = $FIRST_ROW + $data.Count - 1

# Сумма достигнутой выработки, кг (служебная колонка 39) — идёт в шапку.
$achieved = 0.0
foreach ($r in $data) { if ($r.Count -ge 39 -and $r[38]) { $achieved += [double]($r[38] -replace ',', '.') } }

# --- готовим массив значений для листа ---
$vals = New-Object 'object[,]' $data.Count, $COLS
for ($i = 0; $i -lt $data.Count; $i++) {
  for ($c = 0; $c -lt $COLS; $c++) {
    $raw = if ($c -lt $data[$i].Count) { $data[$i][$c] } else { '' }
    if ($raw -eq '') { $vals[$i, $c] = $null; continue }
    $num = 0.0
    if ([double]::TryParse(($raw -replace ',', '.'), [Globalization.NumberStyles]::Float,
                           [Globalization.CultureInfo]::InvariantCulture, [ref]$num)) {
      $vals[$i, $c] = $num
    } else {
      $vals[$i, $c] = $raw
    }
  }
}

# --- заполняем копию шаблона ---
$stamp = ($Day -replace '\.', '-')
$out = Join-Path $OutDir "Production Report $stamp.xlsx"
$tmp = Join-Path $env:TEMP "report_tmp_$stamp`_$([guid]::NewGuid().ToString('N'))$([IO.Path]::GetExtension($Template))"
Copy-Item $Template $tmp -Force
# копия наследует атрибуты оригинала: снимаем «только чтение», иначе Excel не даст писать
Set-ItemProperty -Path $tmp -Name IsReadOnly -Value $false -ErrorAction SilentlyContinue

$xl = New-Object -ComObject Excel.Application
$xl.Visible = $false
$xl.DisplayAlerts = $false
try {
  $wb = $xl.Workbooks.Open($tmp, 0, $false)
  $ws = $wb.Worksheets.Item(1)
  # шаблон может быть защищён от изменений — снимаем защиту у копии
  try { $wb.Unprotect() } catch {}
  try { $ws.Unprotect() } catch {}

  # чистим прежние данные станков, формулы восстановим ниже
  # фигурные скобки обязательны: иначе "$FIRST_ROW:AK45" читается как переменная области видимости
  $ws.Range("A${FIRST_ROW}:AK45").ClearContents() | Out-Null

  $ws.Range("A$FIRST_ROW").Resize($data.Count, $COLS).Value2 = $vals

  # штатные формулы шаблона: 100% Prod. Kg, Effic Total и суммы обрывов
  for ($i = 0; $i -lt $data.Count; $i++) {
    $r = $FIRST_ROW + $i
    $ws.Cells.Item($r, 7).Formula  = "=F$r*E$r*(C$r*24*60/D$r)"   # G: 100% Prod. Kg
    $ws.Cells.Item($r, 21).Formula = "=AVERAGE(R${r}:T${r})"      # U: Effic Total
    $ws.Cells.Item($r, 25).Formula = "=X$r+W$r+V$r"               # Y: Pile Total
    $ws.Cells.Item($r, 29).Formula = "=AB$r+AA$r+Z$r"             # AC: Weft Total
    $ws.Cells.Item($r, 33).Formula = "=AF$r+AE$r+AD$r"            # AG: Ground Total
  }

  # Среднее время одного останова (mending), секунды — колонки AR:AZ.
  # Правее блока Design (program), поэтому существующие формулы не затрагиваются.
  $MEND_COL = 44          # AR
  $ws.Cells.Item(4, $MEND_COL).Value2      = "Mending time, sek"
  $ws.Cells.Item(4, $MEND_COL + 3).Value2  = "Mending time, sek"
  $ws.Cells.Item(4, $MEND_COL + 6).Value2  = "Mending time, sek"
  $titles = @("Vors A", "Vors B", "Vors C", "Utog A", "Utog B", "Utog C", "Karenoy A", "Karenoy B", "Karenoy C")
  for ($i = 0; $i -lt 9; $i++) { $ws.Cells.Item(5, $MEND_COL + $i).Value2 = $titles[$i] }

  $mend = New-Object 'object[,]' $data.Count, 9
  for ($i = 0; $i -lt $data.Count; $i++) {
    for ($c = 0; $c -lt 9; $c++) {
      $raw = if (($c + 39) -lt $data[$i].Count) { $data[$i][$c + 39] } else { '' }
      $num = 0.0
      if ($raw -ne '' -and [double]::TryParse(($raw -replace ',', '.'), [Globalization.NumberStyles]::Float,
                                              [Globalization.CultureInfo]::InvariantCulture, [ref]$num)) {
        $mend[$i, $c] = $num
      } else { $mend[$i, $c] = $null }
    }
  }
  $ws.Cells.Item($FIRST_ROW, $MEND_COL).Resize($data.Count, 9).Value2 = $mend
  # без этого Excel показывает решётки вместо чисел: колонки узкие по умолчанию
  $ws.Range($ws.Cells.Item(5, $MEND_COL), $ws.Cells.Item(45, $MEND_COL + 8)).EntireColumn.AutoFit() | Out-Null

  # шапка: достигнутая выработка (J2) и дата отчёта
  $ws.Range("J2").Value2 = [math]::Round($achieved, 1)
  $dateCell = $ws.Cells.Item(4, 42)
  if ($dateCell.Text -match '^\d{2}[,.]\d{2}[,.]\d{4}$' -or $dateCell.Text -eq '') {
    $p = $Day -split '\.'
    $dateCell.Value2 = "$($p[2]),$($p[1]),$($p[0])"
  }

  $wb.SaveAs($out, 51)                                            # 51 = .xlsx
  $prod100 = $ws.Range("J1").Text
  $eff = $ws.Range("J3").Text
  Write-Output "Готово: $out"
  Write-Output "  станков: $($data.Count)"
  Write-Output "  100% Production: $prod100 кг"
  Write-Output "  Achieved Production: $([math]::Round($achieved)) кг"
  Write-Output "  Production Efficiency: $eff %"
}
finally {
  if ($wb) { $wb.Close($false) }
  $xl.Quit()
  [void][Runtime.InteropServices.Marshal]::ReleaseComObject($xl)
  Remove-Item $tmp -Force -ErrorAction SilentlyContinue
}
