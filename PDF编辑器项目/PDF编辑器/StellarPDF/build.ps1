$ErrorActionPreference = 'Stop'
$project = $PSScriptRoot
$root = Split-Path $project -Parent
$python = Join-Path $project '.venv\Scripts\python.exe'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYINSTALLER_CONFIG_DIR = Join-Path $project '.pyinstaller'
$env:TEMP = Join-Path $project '.tmp_build'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Force -Path $env:PYINSTALLER_CONFIG_DIR, $env:TEMP | Out-Null

Push-Location $project
try {
    if (-not (Test-Path $python)) { throw "找不到虚拟环境：$python" }
    & $python -m PyInstaller --noconfirm --clean --workpath 'build' --distpath 'dist' 'StellarPDF.spec'
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller 退出码 $LASTEXITCODE" }
    $built = Join-Path $project 'dist\星澜PDF.exe'
    if (-not (Test-Path $built)) { throw "构建失败：找不到 $built" }
    $bin = Join-Path $project 'bin'
    New-Item -ItemType Directory -Force -Path $bin | Out-Null
    $actual = Join-Path $bin '星澜PDF_主程序.exe'
    Copy-Item -LiteralPath $built -Destination $actual -Force
    $csc = 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe'
    if (-not (Test-Path $csc)) { throw "找不到 C# 编译器：$csc" }
    $launcherSource = Join-Path $project 'launcher\Program.cs'
    $target = Join-Path $root '星澜PDF.exe'
    & $csc /nologo /target:winexe /platform:anycpu /codepage:65001 `
        "/win32icon:$(Join-Path $project 'app\assets\app.ico')" `
        /reference:System.dll /reference:System.Windows.Forms.dll `
        "/out:$target" $launcherSource
    if ($LASTEXITCODE -ne 0) { throw "启动器编译失败" }
    $size = [math]::Round((Get-Item $actual).Length / 1MB, 1)
    Write-Host "构建完成：启动器 $target；主程序 $actual ($size MB)"
}
finally {
    Pop-Location
}
