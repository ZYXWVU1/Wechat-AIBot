$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Python launcher 'py' was not found. Install Python 3.10 x64 first."
}

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    py -3.10 -m venv .venv
}

& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt

$existingKey = [Environment]::GetEnvironmentVariable("WCF_BRIDGE_KEY", "User")
if ([string]::IsNullOrWhiteSpace($existingKey)) {
    $generatedKey = & .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
    [Environment]::SetEnvironmentVariable("WCF_BRIDGE_KEY", $generatedKey, "User")
    Write-Host "A new WCF_BRIDGE_KEY was generated and stored for the current user."
} else {
    Write-Host "Existing WCF_BRIDGE_KEY retained."
}

if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable("WCF_BRIDGE_PORT", "User"))) {
    [Environment]::SetEnvironmentVariable("WCF_BRIDGE_PORT", "8787", "User")
}
if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable("WCF_ALLOWED_RECEIVERS", "User"))) {
    [Environment]::SetEnvironmentVariable("WCF_ALLOWED_RECEIVERS", "filehelper", "User")
}

Write-Host "Setup complete. Configure WCF_BRIDGE_HOST before running run_bridge.ps1."
