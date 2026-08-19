<#
.SYNOPSIS
    Run this before ending a work session so nothing gets lost.

.DESCRIPTION
    Stages everything, commits with a timestamp, and pushes to both remote
    backup branches (origin/amrr_waell and origin/amr_wael). Safe to run
    even if there's nothing new — it just reports that and exits.

    This is a git commit + push wrapper, not a substitute for git itself:
    review `git status` yourself first if you want to leave something out
    of the snapshot (this script stages everything with `git add -A`).

.USAGE
    From the repo root, in PowerShell:
        .\scripts\backup.ps1
    Or with a custom message:
        .\scripts\backup.ps1 -Message "finished the DQN policy comparison"
#>
param(
    [string]$Message = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

Write-Host "== Backup: $repoRoot ==" -ForegroundColor Cyan

git add -A

$staged = git diff --cached --name-only
if (-not $staged) {
    Write-Host "Nothing to commit — working tree already matches the last commit." -ForegroundColor Yellow
} else {
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm"
    $commitMessage = if ($Message) { "Backup $timestamp - $Message" } else { "Backup $timestamp" }
    Write-Host "Committing $($staged.Count) changed file(s): $commitMessage" -ForegroundColor Green
    git commit -m $commitMessage
}

$branch = git branch --show-current
Write-Host "Pushing '$branch' to origin..." -ForegroundColor Cyan

git push origin $branch
if ($LASTEXITCODE -ne 0) {
    Write-Host "Push to origin/$branch failed — see the error above. If it's a sign-in prompt, complete it and re-run this script." -ForegroundColor Red
    exit 1
}

# Keep the secondary branch (amr_wael) in sync too, if it's not the branch we're already on.
if ($branch -ne "amr_wael") {
    Write-Host "Syncing origin/amr_wael to match..." -ForegroundColor Cyan
    git push origin "${branch}:amr_wael"
}

Write-Host "== Backup complete. Code, data, and models are on GitHub. ==" -ForegroundColor Green
