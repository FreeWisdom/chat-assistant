param(
    [string]$PythonExecutable = "python",
    [switch]$SkipFrontend,
    [switch]$CheckUpstream
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$BackendTests = Join-Path $Root "backend\tests"
$BackendSource = Join-Path $Root "backend\src"
$AdminUi = Join-Path $Root "admin-ui"
$LockFile = Join-Path $Root "config\wxauto4.lock.json"

function Invoke-Checked {
    param(
        [string]$Name,
        [scriptblock]$Command
    )

    Write-Host "`n==> $Name" -ForegroundColor Cyan
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE"
    }
    Write-Host "[PASS] $Name" -ForegroundColor Green
}

if (-not (Get-Command $PythonExecutable -ErrorAction SilentlyContinue)) {
    throw "Python executable was not found: $PythonExecutable"
}

Write-Host "Running side-effect-free project self-tests." -ForegroundColor Cyan
Write-Host "The bot will not start and no WeChat message will be read or sent."

Invoke-Checked "wxauto4 lock and backend tests" {
    & $PythonExecutable -B -m pytest $BackendTests -q -p no:cacheprovider
}

$sourceCheck = @'
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
files = sorted(root.rglob("*.py"))
for path in files:
    source = path.read_text(encoding="utf-8")
    compile(source, str(path), "exec")
print(f"compiled_files={len(files)}")
'@

Invoke-Checked "Python source compilation" {
    $sourceCheck | & $PythonExecutable -B - $BackendSource
}

if ($CheckUpstream) {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        throw "git is required when -CheckUpstream is used."
    }

    $lock = Get-Content -Raw -LiteralPath $LockFile | ConvertFrom-Json
    $remoteOutput = & git ls-remote $lock.repository "refs/heads/$($lock.branch)"
    if ($LASTEXITCODE -ne 0 -or -not $remoteOutput) {
        throw "Unable to read wxauto4 upstream state."
    }
    $remoteCommit = (($remoteOutput | Select-Object -First 1) -split "\s+")[0].ToLowerInvariant()
    if ($remoteCommit -ne $lock.commit.ToLowerInvariant()) {
        throw "wxauto4 is not current: lock=$($lock.commit), upstream=$remoteCommit. Run .\scripts\sync-wxauto4.ps1"
    }
    Write-Host "[PASS] wxauto4 lock matches upstream $($lock.branch)" -ForegroundColor Green
}

if (-not $SkipFrontend) {
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        throw "npm was not found. Install Node.js or run with -SkipFrontend."
    }

    Invoke-Checked "Admin UI production build" {
        Push-Location $AdminUi
        try {
            & npm run build
        } finally {
            Pop-Location
        }
    }
}

if (Get-Command git -ErrorAction SilentlyContinue) {
    Invoke-Checked "Git whitespace validation" {
        & git -C $Root diff --check
    }
}

Write-Host "`nAll self-tests passed." -ForegroundColor Green
