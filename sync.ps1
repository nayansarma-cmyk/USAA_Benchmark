# Commit all changes and push to GitHub.   Usage:  .\sync.ps1 "what changed"
param([string]$Message = "Update $(Get-Date -Format 'yyyy-MM-dd HH:mm')")
$ErrorActionPreference = "Stop"
$Remote = "https://github.com/nayansarma-cmyk/USAA_Benchmark.git"
Set-Location $PSScriptRoot

$git = (Get-Command git -ErrorAction SilentlyContinue).Source
if (-not $git) {
    $git = @("C:\Program Files\Git\cmd\git.exe", "$env:LOCALAPPDATA\Programs\Git\cmd\git.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $git) { throw "git not found. Install Git for Windows (https://git-scm.com/download/win) and re-run." }

if (-not (Test-Path .git)) { & $git init -b main | Out-Null }
if (-not ((& $git remote) -contains "origin")) { & $git remote add origin $Remote }

# Safety net: refuse to continue if a secrets file would be committed.
& $git add -A
$staged = & $git diff --cached --name-only
$leak = $staged | Where-Object { $_ -match '(^|/)\.env' -or $_ -match '\.(key|pem)$' -or $_ -match '^node_modules/' }
if ($leak) { & $git reset | Out-Null; throw "Refusing to commit secrets: $($leak -join ', ')" }

if ($staged) { & $git commit -m $Message | Out-Null; Write-Host "Committed: $Message" } else { Write-Host "Nothing new to commit." }

# Reconcile with commits already on the remote (e.g. a README created on GitHub), then push.
& $git fetch origin 2>&1 | Out-Null
if ($LASTEXITCODE -eq 0 -and (& $git branch -r) -match "origin/main") {
    & $git pull --rebase origin main --allow-unrelated-histories
    if ($LASTEXITCODE -ne 0) { throw "Rebase hit a conflict. Resolve it (git status), run 'git rebase --continue', then re-run." }
}
& $git push -u origin main
if ($LASTEXITCODE -ne 0) { throw "Push FAILED (exit $LASTEXITCODE). If it says 'could not read Username', run this script in your own PowerShell window so GitHub sign-in can open." }
Write-Host "Pushed to $Remote"
