// ─────────────────────────────────────────────────────────────────────────────
// Enterprise GenAI Platform — root deployment
// Scope: subscription (creates RG + calls per-RG modules)
//
// Phase 1 scope:
//   - Resource group
//   - Azure OpenAI account (Managed Identity enabled, local auth disabled)
//   - Three model deployments: gpt-4o-mini, gpt-4.1-mini, gpt-4.1-nano  (low TPM caps)
//   - RBAC: "Cognitive Services OpenAI User" granted to a principal
//
// Run:
//   az deployment sub create `
//     --name genai-$(Get-Date -Format yyyyMMddHHmm) `
//     --location eastus2 `
//     --template-file infra/main.bicep `
//     --parameters infra/main.parameters.json `
//     --parameters principalId=$(az ad signed-in-user show --query id -o tsv)
// ─────────────────────────────────────────────────────────────────────────────

targetScope = 'subscription'

@description('Azure region for all resources. Pick one with gpt-4.1 quota: eastus2, swedencentral, westus3.')
param location string = 'eastus2'

@description('Short environment tag — used in resource names and tags.')
@allowed([ 'dev', 'test', 'prod' ])
param environment string = 'dev'

@description('Resource group name.')
param resourceGroupName string = 'rg-genai-${environment}'

@description('Azure OpenAI account name. Must be globally unique (becomes <name>.openai.azure.com).')
param openAiAccountName string = 'aoai-genai-${environment}-${uniqueString(subscription().id, resourceGroupName)}'

@description('Foundry project name (child resource under the AI Services account).')
param foundryProjectName string = 'proj-genai-${environment}'

@description('AAD object id that should receive the "Cognitive Services OpenAI User" role (your user or an app/MI principalId).')
param principalId string

@description('Type of the principal receiving the role.')
@allowed([ 'User', 'ServicePrincipal', 'Group' ])
param principalType string = 'User'

@description('Disable API-key auth on the AOAI account — forces all callers to use Managed Identity / AAD.')
param disableLocalAuth bool = true

@description('Provision Grounding with Bing Search (Bing account + Foundry project connection). Requires a PAYG/EA/MCA/CSP subscription — the G1 SKU is NOT eligible on MSDN/Visual Studio subscriptions.')
param enableBingGrounding bool = false

@description('Bing Grounding account name. Must be globally unique.')
param bingAccountName string = 'bing-genai-${environment}-${uniqueString(subscription().id, resourceGroupName)}'

@description('Model deployments to create. Capacity is in units of 1K TPM (10 = 10K TPM).')
param deployments array = [
  {
    name: 'gpt-4o-mini-test'
    modelName: 'gpt-4o-mini'
    modelVersion: '2024-07-18'
    skuName: 'GlobalStandard'
    skuCapacity: 10
  }
  {
    name: 'gpt-4.1-mini-test'
    modelName: 'gpt-4.1-mini'
    modelVersion: '2025-04-14'
    skuName: 'GlobalStandard'
    skuCapacity: 10
  }
  {
    name: 'gpt-4.1-nano'
    modelName: 'gpt-4.1-nano'
    modelVersion: '2025-04-14'
    skuName: 'GlobalStandard'
    skuCapacity: 10
  }
]

param tags object = {
  project: 'enterprise-genai-platform'
  environment: environment
  managedBy: 'bicep'
  costCenter: 'genai-test'
}

// ── Resource group ──────────────────────────────────────────────────────────
resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: resourceGroupName
  location: location
  tags: tags
}

// ── Azure OpenAI module ─────────────────────────────────────────────────────
module openai 'openai.bicep' = {
  name: 'openai-deploy'
  scope: rg
  params: {
    location: location
    accountName: openAiAccountName
    projectName: foundryProjectName
    disableLocalAuth: disableLocalAuth
    deployments: deployments
    principalId: principalId
    principalType: principalType
    tags: tags
  }
}

// ── Grounding with Bing Search module (runs after the Foundry project) ─────
module bing 'bing.bicep' = if (enableBingGrounding) {
  name: 'bing-deploy'
  scope: rg
  params: {
    accountName: openAiAccountName
    projectName: foundryProjectName
    bingAccountName: bingAccountName
    tags: tags
  }
  dependsOn: [
    openai
  ]
}

// ── Outputs (used by deploy.ps1 to populate .env) ──────────────────────────
output resourceGroupName string = rg.name
output openAiEndpoint string = openai.outputs.endpoint
output openAiAccountName string = openai.outputs.accountName
output foundryProjectName string = openai.outputs.projectName
output foundryProjectEndpoint string = openai.outputs.projectEndpoint
output foundryPortalUrl string = openai.outputs.foundryPortalUrl
output deploymentNames array = openai.outputs.deploymentNames
output recommendedDeployment string = openai.outputs.deploymentNames[0]

// Bing grounding (empty strings when disabled — deploy.ps1 handles both).
output bingGroundingEnabled bool = enableBingGrounding
output bingConnectionId string = enableBingGrounding ? (bing.?outputs.connectionId ?? '') : ''
output bingGroundingEndpoint string = enableBingGrounding ? openai.outputs.projectEndpoint : ''
