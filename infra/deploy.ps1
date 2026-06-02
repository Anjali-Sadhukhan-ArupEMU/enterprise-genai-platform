# ─────────────────────────────────────────────────────────────────────────────
# Provisioning wrapper for the GenAI Platform Azure resources.
#
# What it does:
#   1. Verifies you're logged in with the right subscription
#   2. Resolves your AAD object id (so role assignment lands on YOU)
#   3. Runs `az deployment sub create` with the Bicep template
#   4. Writes deployment outputs into backend/.env for the FastAPI app
#
# Usage:
#   .\infra\deploy.ps1                          # uses main.parameters.json
#   .\infra\deploy.ps1 -Environment test        # overrides environment tag
#   .\infra\deploy.ps1 -WhatIf                  # preview only, no changes
# ─────────────────────────────────────────────────────────────────────────────

[CmdletBinding()]
param(
    [string] $Environment = 'dev',
    [string] $Location = 'eastus2',
    [string] $ParameterFile = (Join-Path $PSScriptRoot 'main.parameters.json'),
    [string] $TemplateFile = (Join-Path $PSScriptRoot 'main.bicep'),
    # Pre-resolved AAD object id — bypasses the Graph lookup. Get it via portal:
    # Entra ID → Users → your name → Object ID. Useful when Graph is unreachable.
    [string] $PrincipalId = '',
    [switch] $WhatIf
)

$ErrorActionPreference = 'Stop'

# ── 1. Sanity check sign-in ─────────────────────────────────────────────────
Write-Host "→ Checking Azure CLI sign-in..." -ForegroundColor Cyan
$ctx = az account show 2>$null | ConvertFrom-Json
if (-not $ctx) {
    throw "Not signed in. Run 'az login' first."
}
Write-Host "  Subscription : $($ctx.name)" -ForegroundColor Gray
Write-Host "  Tenant       : $($ctx.tenantId)" -ForegroundColor Gray
Write-Host "  User         : $($ctx.user.name)" -ForegroundColor Gray

# ── 2. Resolve principal id (with retry, or bypass if -PrincipalId given) ──
$principalId = $PrincipalId
if (-not $principalId) {
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        try {
            $principalId = az ad signed-in-user show --query id -o tsv 2>$null
            if ($principalId) { break }
        }
        catch {}
        Write-Host "  Graph call attempt $attempt failed, retrying in 5s..." -ForegroundColor Yellow
        Start-Sleep -Seconds 5
    }
    if (-not $principalId) {
        throw @"
Failed to resolve AAD object id for $($ctx.user.name) via Graph (transient network issue).

Workaround — pass it explicitly:
  1. Portal → Entra ID → Users → search '$($ctx.user.name)' → copy Object ID
  2. Re-run: .\infra\deploy.ps1 -PrincipalId <that-object-id>
"@
    }
}
Write-Host "  principalId  : $principalId" -ForegroundColor Gray

# ── 2b. Ensure the Microsoft.Bing RP is registered (Grounding with Bing) ───
Write-Host "→ Ensuring Microsoft.Bing resource provider is registered..." -ForegroundColor Cyan
$bingState = az provider show --namespace Microsoft.Bing --query registrationState -o tsv 2>$null
if ($bingState -ne 'Registered') {
    Write-Host "  Registering Microsoft.Bing (was '$bingState')..." -ForegroundColor Yellow
    az provider register --namespace Microsoft.Bing | Out-Null
}
else {
    Write-Host "  Microsoft.Bing already registered." -ForegroundColor Gray
}

# ── 3. Deploy ───────────────────────────────────────────────────────────────
$deployName = "genai-$Environment-$(Get-Date -Format 'yyyyMMddHHmm')"
$action = if ($WhatIf) { 'what-if' } else { 'create' }
Write-Host "`n→ Running 'az deployment sub $action' as '$deployName'..." -ForegroundColor Cyan

$cmd = @(
    'az', 'deployment', 'sub', $action,
    '--name', $deployName,
    '--location', $Location,
    '--template-file', $TemplateFile,
    '--parameters', $ParameterFile,
    '--parameters', "principalId=$principalId", "environment=$Environment"
)
& $cmd[0] $cmd[1..($cmd.Length - 1)]
if ($LASTEXITCODE -ne 0) { throw "Deployment failed (exit $LASTEXITCODE)." }
if ($WhatIf) { return }

# ── 4. Fetch outputs ────────────────────────────────────────────────────────
Write-Host "`n→ Fetching deployment outputs..." -ForegroundColor Cyan
$outputs = az deployment sub show --name $deployName --query properties.outputs | ConvertFrom-Json
$endpoint = $outputs.openAiEndpoint.value
$deployment = $outputs.recommendedDeployment.value
$account = $outputs.openAiAccountName.value
$rg = $outputs.resourceGroupName.value
$projectName = $outputs.foundryProjectName.value
$projectEp = $outputs.foundryProjectEndpoint.value
$portalUrl = $outputs.foundryPortalUrl.value
$bingEnabled = $outputs.bingGroundingEnabled.value
$bingConnId = $outputs.bingConnectionId.value
$bingEndpoint = $outputs.bingGroundingEndpoint.value

Write-Host "  RG               : $rg"          -ForegroundColor Gray
Write-Host "  Foundry account  : $account"     -ForegroundColor Gray
Write-Host "  Foundry project  : $projectName" -ForegroundColor Gray
Write-Host "  OpenAI endpoint  : $endpoint"    -ForegroundColor Gray
Write-Host "  Project endpoint : $projectEp"   -ForegroundColor Gray
Write-Host "  Portal           : $portalUrl"   -ForegroundColor Gray
Write-Host "  Deployment       : $deployment"  -ForegroundColor Gray
if ($bingEnabled) {
    Write-Host "  Bing grounding   : $bingConnId" -ForegroundColor Gray
}

# ── 5. Patch backend/.env (creates if missing) ──────────────────────────────
$envFile = Join-Path (Split-Path $PSScriptRoot -Parent) '.env'
if (-not (Test-Path $envFile)) {
    Copy-Item (Join-Path (Split-Path $PSScriptRoot -Parent) '.env.example') $envFile
    Write-Host "  Created $envFile from .env.example" -ForegroundColor Yellow
}

function Set-EnvVar {
    param([string]$Key, [string]$Value)
    $content = Get-Content $envFile -Raw
    $line = "$Key=$Value"
    if ($content -match "(?m)^$Key=.*$") {
        $content = [regex]::Replace($content, "(?m)^$Key=.*$", $line)
    }
    else {
        $content = $content.TrimEnd() + "`r`n$line`r`n"
    }
    # Retry on transient file locks (uvicorn reloader, VS Code save-on-focus)
    $attempts = 0
    while ($true) {
        try {
            [System.IO.File]::WriteAllText($envFile, $content)
            break
        }
        catch [System.IO.IOException] {
            $attempts++
            if ($attempts -ge 5) {
                Write-Host "  ! Could not write $envFile after 5 tries — close any editor/process holding it, then run the snippet below manually." -ForegroundColor Yellow
                $script:EnvWriteFailed = $true
                return
            }
            Start-Sleep -Milliseconds 400
        }
    }
}

$script:EnvWriteFailed = $false
Set-EnvVar 'AZURE_OPENAI_ENDPOINT'                $endpoint
Set-EnvVar 'AZURE_OPENAI_DEPLOYMENT'              $deployment
Set-EnvVar 'AZURE_OPENAI_USE_MANAGED_IDENTITY'    'true'
Set-EnvVar 'AZURE_OPENAI_API_KEY'                 ''
Set-EnvVar 'FOUNDRY_PROJECT_ENDPOINT'             $projectEp
if ($bingEnabled) {
    Set-EnvVar 'WEB_SEARCH_ENABLED'               'true'
    Set-EnvVar 'BING_GROUNDING_CONNECTION_ID'     $bingConnId
    Set-EnvVar 'BING_GROUNDING_ENDPOINT'          $bingEndpoint
}

if ($script:EnvWriteFailed) {
    Write-Host "`nPaste this into .env manually:" -ForegroundColor Yellow
    Write-Host "  AZURE_OPENAI_ENDPOINT=$endpoint"             -ForegroundColor Gray
    Write-Host "  AZURE_OPENAI_DEPLOYMENT=$deployment"         -ForegroundColor Gray
    Write-Host "  AZURE_OPENAI_USE_MANAGED_IDENTITY=true"      -ForegroundColor Gray
    Write-Host "  AZURE_OPENAI_API_KEY="                       -ForegroundColor Gray
    Write-Host "  FOUNDRY_PROJECT_ENDPOINT=$projectEp"         -ForegroundColor Gray
    if ($bingEnabled) {
        Write-Host "  WEB_SEARCH_ENABLED=true"                       -ForegroundColor Gray
        Write-Host "  BING_GROUNDING_CONNECTION_ID=$bingConnId"      -ForegroundColor Gray
        Write-Host "  BING_GROUNDING_ENDPOINT=$bingEndpoint"         -ForegroundColor Gray
    }
}
else {
    Write-Host "  Updated $envFile" -ForegroundColor Green
}

Write-Host "`n✓ Done. Restart the backend to pick up the new .env." -ForegroundColor Green
Write-Host "  Foundry portal: $portalUrl" -ForegroundColor Cyan
Write-Host "  Next: .\.venv\Scripts\Activate.ps1; uvicorn backend.main:app --reload" -ForegroundColor Gray
