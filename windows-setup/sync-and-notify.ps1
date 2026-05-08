# sync-and-notify.ps1
# memsearch Auto-Sync & Notification Script for Windows
# Run via Task Scheduler to detect GitHub updates and auto-sync

$ErrorActionPreference = "SilentlyContinue"
$repoPath = "$HOME\Desktop\trade"
$logFile = "$repoPath\windows-setup\sync.log"
$memsearchDir = "$repoPath\.memsearch\memory"

function Write-Log {
    param($Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$timestamp | $Message" | Out-File -Append -FilePath $logFile
}

function Show-WindowsNotification {
    param($Title, $Message)
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
    $textNodes = $template.GetElementsByTagName("text")
    $textNodes[0].AppendChild($template.CreateTextNode($Title)) | Out-Null
    $textNodes[1].AppendChild($template.CreateTextNode($Message)) | Out-Null
    $toast = [Windows.UI.Notifications.ToastNotification]::new($template)
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("memsearch Sync").Show($toast)
}

function Show-FallbackNotification {
    param($Title, $Message)
    # Fallback: Write to event log and create a visible marker file
    Write-EventLog -LogName Application -Source "memsearch Sync" -EventId 1001 -EntryType Information -Message "$Title`: $Message" -ErrorAction SilentlyContinue
    $markerFile = "$env:TEMP\memsearch-sync-notification.txt"
    "$Title`n$Message`n$(Get-Date)" | Out-File -FilePath $markerFile
    Write-Log "Notification written to $markerFile"
}

Write-Log "=== Sync check started ==="

# Check if repo exists
if (-not (Test-Path $repoPath)) {
    Write-Log "ERROR: Repository not found at $repoPath"
    exit 1
}

# Navigate to repo
Set-Location $repoPath

# Check git status
$beforeHash = git rev-parse HEAD 2>$null
if (-not $beforeHash) {
    Write-Log "ERROR: Not a git repository"
    exit 1
}

# Pull latest changes
Write-Log "Pulling latest changes from GitHub..."
$pullOutput = git pull 2>&1
$pullExitCode = $LASTEXITCODE

if ($pullExitCode -ne 0) {
    Write-Log "ERROR: git pull failed - $pullOutput"
    Show-FallbackNotification -Title "memsearch Sync Error" -Message "Failed to pull from GitHub. Check network connection."
    exit 1
}

# Check if anything changed
$afterHash = git rev-parse HEAD
if ($beforeHash -eq $afterHash) {
    Write-Log "No changes detected. Skipping."
    exit 0
}

Write-Log "New commits detected. Syncing..."

# Check if memsearch is installed
$memsearchCmd = Get-Command memsearch -ErrorAction SilentlyContinue
if (-not $memsearchCmd) {
    Write-Log "memsearch not found. Running setup.bat..."
    Start-Process -FilePath "$repoPath\windows-setup\setup.bat" -Wait -WindowStyle Hidden
}

# Re-index memory files if they exist
if (Test-Path $memsearchDir) {
    Write-Log "Re-indexing memory files..."
    memsearch index "$memsearchDir" 2>&1 | Out-Null
    $indexResult = memsearch stats 2>&1
    Write-Log "Index stats: $indexResult"
}

# Check for new memory files
$newMemoryFiles = Get-ChildItem -Path $memsearchDir -Filter "*.md" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 3
if ($newMemoryFiles) {
    $fileNames = ($newMemoryFiles | ForEach-Object { $_.Name }) -join ", "
    Write-Log "Memory files synced: $fileNames"
    Show-FallbackNotification -Title "memsearch Sync Complete" -Message "New memories synced: $fileNames"
} else {
    Write-Log "Sync complete. No memory files yet."
    Show-FallbackNotification -Title "memsearch Sync Complete" -Message "Repository updated. Run OpenCode/Claude Code to start capturing memories."
}

Write-Log "=== Sync check finished ==="
