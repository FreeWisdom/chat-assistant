param(
    [string]$PythonExecutable = "python",
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Repository = "https://github.com/FreeWisdom/wxauto-4.0.git"
$Branch = "main"
$Ref = "refs/heads/$Branch"
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "git is required to synchronize wxauto4."
}

if (-not (Get-Command $PythonExecutable -ErrorAction SilentlyContinue)) {
    throw "Python executable was not found: $PythonExecutable"
}

$remoteOutput = & git ls-remote $Repository $Ref
if ($LASTEXITCODE -ne 0 -or -not $remoteOutput) {
    throw "Unable to resolve $Repository $Ref"
}

$latestCommit = (($remoteOutput | Select-Object -First 1) -split "\s+")[0].ToLowerInvariant()
if ($latestCommit -notmatch "^[0-9a-f]{40}$") {
    throw "Invalid commit returned by git ls-remote: $latestCommit"
}

$pinFiles = @(
    (Join-Path $Root "backend\requirements.txt"),
    (Join-Path $Root "backend\pyproject.toml")
)
$pinPattern = "((?:https://github\.com/)?FreeWisdom/wxauto-4\.0(?:\.git)?@)[0-9a-fA-F]{40}"

foreach ($path in $pinFiles) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Expected wxauto4 pin file is missing: $path"
    }

    $content = [System.IO.File]::ReadAllText($path)
    if (-not [regex]::IsMatch($content, $pinPattern)) {
        throw "No wxauto4 commit pin found in: $path"
    }

    $updated = [regex]::Replace(
        $content,
        $pinPattern,
        [System.Text.RegularExpressions.MatchEvaluator]{
            param($match)
            return $match.Groups[1].Value + $latestCommit
        }
    )
    [System.IO.File]::WriteAllText($path, $updated, $Utf8NoBom)
}

$lockPath = Join-Path $Root "config\wxauto4.lock.json"
$lockJson = @"
{
  "repository": "$Repository",
  "branch": "$Branch",
  "commit": "$latestCommit"
}
"@
[System.IO.File]::WriteAllText($lockPath, $lockJson, $Utf8NoBom)

Write-Host "wxauto4 upstream commit: $latestCommit" -ForegroundColor Cyan
Write-Host "Project dependency pins and lock file are synchronized." -ForegroundColor Green

if ($SkipInstall) {
    Write-Host "Installation skipped by -SkipInstall."
    exit 0
}

# Remove editable or stale installations first. Otherwise Python can silently
# import a sibling checkout instead of the commit pinned by this project.
& $PythonExecutable -m pip uninstall -y wxauto4
if ($LASTEXITCODE -ne 0) {
    throw "Failed to remove the existing wxauto4 installation."
}

$packageSpec = "wxauto4 @ git+$Repository@$latestCommit"
& $PythonExecutable -m pip install --no-cache-dir $packageSpec
if ($LASTEXITCODE -ne 0) {
    throw "Failed to install wxauto4 commit $latestCommit."
}

# Refresh editable metadata for this project without resolving dependencies a
# second time.
& $PythonExecutable -m pip install --no-deps -e (Join-Path $Root "backend")
if ($LASTEXITCODE -ne 0) {
    throw "Failed to refresh the ai_ta_bot editable installation."
}

$verification = @'
import json
import sys
from importlib import metadata
from pathlib import Path

import wxauto4

expected = sys.argv[1].lower()
distribution = metadata.distribution("wxauto4")
direct_url_text = distribution.read_text("direct_url.json")
if not direct_url_text:
    raise SystemExit("wxauto4 has no direct_url.json; the installed source cannot be verified")

direct_url = json.loads(direct_url_text)
actual = direct_url.get("vcs_info", {}).get("commit_id", "").lower()
editable = direct_url.get("dir_info", {}).get("editable", False)

if editable:
    raise SystemExit("wxauto4 is still installed from an editable checkout")
if actual != expected:
    raise SystemExit(f"wxauto4 commit mismatch: expected {expected}, installed {actual or '<unknown>'}")

required_exports = (
    "WeChat",
    "WxParam",
    "Moment",
    "HandRaiseReplyWorkflow",
    "ReplyTaskStore",
    "SearchMessageLocator",
)
missing = [name for name in required_exports if not hasattr(wxauto4, name)]
if missing:
    raise SystemExit(f"wxauto4 is missing expected upstream exports: {', '.join(missing)}")

print(f"verified_commit={actual}")
print(f"module={Path(wxauto4.__file__).resolve()}")
'@

$verification | & $PythonExecutable - $latestCommit
if ($LASTEXITCODE -ne 0) {
    throw "wxauto4 runtime verification failed."
}

Write-Host "wxauto4 installation and runtime import were verified." -ForegroundColor Green
