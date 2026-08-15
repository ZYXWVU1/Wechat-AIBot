$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$bridgeKey = [Environment]::GetEnvironmentVariable("WCF_BRIDGE_KEY", "User")
if ([string]::IsNullOrWhiteSpace($bridgeKey)) {
    throw "WCF_BRIDGE_KEY is not configured. Run setup_bridge.ps1 first."
}
$env:WCF_BRIDGE_KEY = $bridgeKey

foreach ($variableName in @("WCF_BRIDGE_HOST", "WCF_BRIDGE_PORT", "WCF_ALLOWED_RECEIVERS", "WCF_DATA_DIR")) {
    $currentValue = [Environment]::GetEnvironmentVariable($variableName, "Process")
    if ([string]::IsNullOrWhiteSpace($currentValue)) {
        $userValue = [Environment]::GetEnvironmentVariable($variableName, "User")
        if (-not [string]::IsNullOrWhiteSpace($userValue)) {
            [Environment]::SetEnvironmentVariable($variableName, $userValue, "Process")
        }
    }
}

if ([string]::IsNullOrWhiteSpace($env:WCF_BRIDGE_HOST)) {
    throw "Set WCF_BRIDGE_HOST to the Windows VM LAN IPv4 address."
}
if ([string]::IsNullOrWhiteSpace($env:WCF_BRIDGE_PORT)) {
    $env:WCF_BRIDGE_PORT = "8787"
}

& .\.venv\Scripts\python.exe -m uvicorn app:app `
    --host $env:WCF_BRIDGE_HOST `
    --port $env:WCF_BRIDGE_PORT `
    --workers 1
