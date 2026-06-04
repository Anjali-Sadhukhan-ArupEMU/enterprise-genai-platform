# ─────────────────────────────────────────────────────────────────────────────
# Deploy the FastAPI backend to Azure Container Apps (replaces Azure Functions).
#
# Why: Azure Functions (func.AsgiFunctionApp) buffers the whole FastAPI response,
# so SSE token streaming arrives "all at once". Container Apps runs the same
# uvicorn Docker image and streams each chunk immediately.
#
# What it does:
#   1. Verifies sign-in + resolves the existing RG resources (AOAI, Log Analytics)
#   2. Creates an Azure Container Registry (idempotent)
#   3. Builds + pushes the backend image with `az acr build` (uses ./Dockerfile)
#   4. Deploys infra/containerapp.bicep (UAMI + env + app + RBAC)
#   5. Patches frontend/.env.production VITE_API_BASE_URL to the new app URL
#
# Usage:
#   .\infra\deploy-containerapp.ps1
#   .\infra\deploy-containerapp.ps1 -Environment dev -Location eastus2
#   .\infra\deploy-containerapp.ps1 -MinReplicas 0      # scale-to-zero (cheaper)
# ─────────────────────────────────────────────────────────────────────────────

[CmdletBinding()]
param(
    [string] $Environment = 'dev',
    [string] $Location = 'eastus2',
    [string] $ResourceGroup = '',
    [string] $OpenAiAccountName = '',
    [string] $LogAnalyticsWorkspaceName = '',
    [string] $AcrName = '',
    [int]    $MinReplicas = 1,
    [int]    $MaxReplicas = 3,
    [string] $ImageTag = '',
    [switch] $SkipBuild,
    [string] $EntraTenantId = 'ba461c38-ace0-48a9-a880-b7f5a6b8f450',
    [string] $EntraClientId = '78ff835c-ce1e-4b0e-a73c-f782c00efa3f',
    [bool]   $DebugMode = $false
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent

# Force UTF-8 so `az acr build`'s colored log stream doesn't crash the Windows
# console (cp1252) with: UnicodeEncodeError: 'charmap' codec can't encode...
$env:PYTHONIOENCODING = 'utf-8'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

# ── 1. Sign-in check ────────────────────────────────────────────────────────
Write-Host "→ Checking Azure CLI sign-in..." -ForegroundColor Cyan
$ctx = az account show 2>$null | ConvertFrom-Json
if (-not $ctx) { throw "Not signed in. Run 'az login' first." }
Write-Host "  Subscription : $($ctx.name)" -ForegroundColor Gray

# ── 2. Resolve RG + existing resources ──────────────────────────────────────
if (-not $ResourceGroup) { $ResourceGroup = "rg-genai-$Environment" }
Write-Host "→ Resource group: $ResourceGroup" -ForegroundColor Cyan

if (-not $OpenAiAccountName) {
    $OpenAiAccountName = az resource list -g $ResourceGroup `
        --resource-type 'Microsoft.CognitiveServices/accounts' `
        --query "[0].name" -o tsv
}
if (-not $OpenAiAccountName) { throw "Could not find an Azure OpenAI account in $ResourceGroup. Pass -OpenAiAccountName." }
Write-Host "  Azure OpenAI : $OpenAiAccountName" -ForegroundColor Gray

if (-not $LogAnalyticsWorkspaceName) {
    $LogAnalyticsWorkspaceName = az resource list -g $ResourceGroup `
        --resource-type 'Microsoft.OperationalInsights/workspaces' `
        --query "[0].name" -o tsv
}
if (-not $LogAnalyticsWorkspaceName) { throw "Could not find a Log Analytics workspace in $ResourceGroup. Pass -LogAnalyticsWorkspaceName." }
Write-Host "  Log Analytics: $LogAnalyticsWorkspaceName" -ForegroundColor Gray

# Pull live values from the existing AOAI account so the app config matches.
$openAiEndpoint = az cognitiveservices account show -g $ResourceGroup -n $OpenAiAccountName `
    --query "properties.endpoint" -o tsv

# ── 3. Container Registry (idempotent) ──────────────────────────────────────
if (-not $AcrName) {
    # ACR names: 5-50 chars, alphanumeric only, globally unique.
    $suffix = ($ctx.id -replace '[^0-9a-f]', '').Substring(0, 8)
    $AcrName = "acrgenai$Environment$suffix"
}
Write-Host "→ Container Registry: $AcrName" -ForegroundColor Cyan
$acrExists = az acr show -n $AcrName -g $ResourceGroup --query "name" -o tsv 2>$null
if (-not $acrExists) {
    Write-Host "  Creating ACR (Basic, admin disabled)..." -ForegroundColor Yellow
    az acr create -g $ResourceGroup -n $AcrName --sku Basic --admin-enabled false | Out-Null
}
else {
    Write-Host "  ACR already exists." -ForegroundColor Gray
}
$acrLoginServer = az acr show -n $AcrName -g $ResourceGroup --query "loginServer" -o tsv

# ── 4. Build + push image (remote build in ACR — no local Docker needed) ────
if (-not $ImageTag) { $ImageTag = if ($SkipBuild) { 'latest' } else { Get-Date -Format 'yyyyMMddHHmmss' } }
$imageRef = "$acrLoginServer/genai-backend:$ImageTag"
if ($SkipBuild) {
    Write-Host "→ Skipping build; reusing image $imageRef" -ForegroundColor Yellow
}
else {
    Write-Host "→ Building image $imageRef ..." -ForegroundColor Cyan
    az acr build -r $AcrName -t "genai-backend:$ImageTag" -t "genai-backend:latest" -f "$repoRoot/Dockerfile" $repoRoot
    if ($LASTEXITCODE -ne 0) { throw "Image build failed (exit $LASTEXITCODE)." }
}

# ── 5. App config from the current Function App (CORS, App Insights, etc.) ──
$swaDefaultHost = az staticwebapp list -g $ResourceGroup --query "[0].defaultHostname" -o tsv 2>$null
$allowedOriginsList = @('http://localhost:3000')
if ($swaDefaultHost) { $allowedOriginsList = @("https://$swaDefaultHost") + $allowedOriginsList }
$allowedOrigins = ($allowedOriginsList | ConvertTo-Json -Compress)

$foundryEndpoint = ''
$appInsightsConn = ''
$fa = az resource list -g $ResourceGroup --resource-type 'Microsoft.Web/sites' `
    --query "[?kind=='functionapp,linux'].name | [0]" -o tsv 2>$null
if ($fa) {
    $faSettings = az functionapp config appsettings list -g $ResourceGroup -n $fa -o json 2>$null | ConvertFrom-Json
    $foundryEndpoint = ($faSettings | Where-Object name -eq 'FOUNDRY_PROJECT_ENDPOINT').value
    $appInsightsConn = ($faSettings | Where-Object name -eq 'APPLICATIONINSIGHTS_CONNECTION_STRING').value
    $faOrigins = ($faSettings | Where-Object name -eq 'ALLOWED_ORIGINS').value
    if ($faOrigins) { $allowedOrigins = $faOrigins }
    $faDeployment = ($faSettings | Where-Object name -eq 'AZURE_OPENAI_DEPLOYMENT').value
}
if (-not $faDeployment) { $faDeployment = 'gpt-4o-mini-test' }

Write-Host "  OpenAI endpoint : $openAiEndpoint"   -ForegroundColor Gray
Write-Host "  Deployment      : $faDeployment"      -ForegroundColor Gray
Write-Host "  Allowed origins : $allowedOrigins"    -ForegroundColor Gray

# ── 6. Deploy the Container App ─────────────────────────────────────────────
# Escape the inner double-quotes of the JSON array so they survive PowerShell ->
# az CLI native argument passing (otherwise `["a","b"]` arrives as `[a,b]`,
# which is invalid JSON and crashes pydantic-settings at startup).
$allowedOriginsParam = $allowedOrigins -replace '"', '\"'

$deployName = "genai-ca-$Environment-$(Get-Date -Format 'yyyyMMddHHmm')"
Write-Host "`n→ Deploying Container App ($deployName)..." -ForegroundColor Cyan
az deployment group create `
    --resource-group $ResourceGroup `
    --name $deployName `
    --template-file (Join-Path $PSScriptRoot 'containerapp.bicep') `
    --parameters `
    location=$Location `
    environment=$Environment `
    acrName=$AcrName `
    containerImage=$imageRef `
    openAiAccountName=$OpenAiAccountName `
    logAnalyticsWorkspaceName=$LogAnalyticsWorkspaceName `
    azureOpenAiEndpoint=$openAiEndpoint `
    azureOpenAiDeployment=$faDeployment `
    foundryProjectEndpoint=$foundryEndpoint `
    allowedOrigins=$allowedOriginsParam `
    entraTenantId=$EntraTenantId `
    entraClientId=$EntraClientId `
    debug=$($DebugMode.ToString().ToLower()) `
    appInsightsConnectionString=$appInsightsConn `
    minReplicas=$MinReplicas `
    maxReplicas=$MaxReplicas
if ($LASTEXITCODE -ne 0) { throw "Container App deployment failed (exit $LASTEXITCODE)." }

# ── 7. Read outputs ─────────────────────────────────────────────────────────
$outputs = az deployment group show -g $ResourceGroup -n $deployName --query properties.outputs | ConvertFrom-Json
$appUrl = $outputs.containerAppUrl.value
$appName = $outputs.containerAppName.value
Write-Host "`n  Container App : $appName" -ForegroundColor Gray
Write-Host "  URL           : $appUrl"  -ForegroundColor Green

# ── 8. Repoint the frontend at the new backend ──────────────────────────────
# API_BASE is the ORIGIN only — call sites already include the /api/v1 path
# (e.g. apiUrl("/api/v1/chat")), so do NOT append /api/v1 here.
$envProd = Join-Path $repoRoot 'frontend/.env.production'
$apiBase = $appUrl
if (Test-Path $envProd) {
    $content = Get-Content $envProd -Raw
    if ($content -match '(?m)^VITE_API_BASE_URL=.*$') {
        $content = [regex]::Replace($content, '(?m)^VITE_API_BASE_URL=.*$', "VITE_API_BASE_URL=$apiBase")
    }
    else {
        $content = $content.TrimEnd() + "`r`nVITE_API_BASE_URL=$apiBase`r`n"
    }
    [System.IO.File]::WriteAllText($envProd, $content)
}
else {
    "VITE_API_BASE_URL=$apiBase`r`n" | Set-Content $envProd
}
Write-Host "  Patched frontend/.env.production → VITE_API_BASE_URL=$apiBase" -ForegroundColor Green

Write-Host "`n✓ Backend is live on Container Apps with true SSE streaming." -ForegroundColor Green
Write-Host "  Health : $appUrl/health" -ForegroundColor Cyan
Write-Host "  Next   : commit frontend/.env.production and push to redeploy the SWA." -ForegroundColor Gray
