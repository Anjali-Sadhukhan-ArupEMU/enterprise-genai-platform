// ─────────────────────────────────────────────────────────────────────────────
// Azure AI Foundry resource + project + model deployments + RBAC
// Scope: resource group (called from main.bicep)
//
// Resource shape (current Foundry model):
//   Microsoft.CognitiveServices/accounts         (kind: AIServices)   ← "Foundry resource"
//     └── projects/<name>                                              ← "Foundry project"
//     └── deployments/<name>  (gpt-4o-mini, gpt-4.1-mini, ...)         ← models in catalog
//
// The OpenAI sub-endpoint (https://<account>.openai.azure.com/) is still
// exposed when kind=AIServices, so the existing AzureOpenAIProvider works
// unchanged. The project endpoint (https://<account>.services.ai.azure.com/api/projects/<proj>)
// is what `azure-ai-projects` / `azure-ai-inference` SDKs talk to for
// non-OpenAI models (Llama, Mistral, DeepSeek).
// ─────────────────────────────────────────────────────────────────────────────

@description('Region.')
param location string

@description('Foundry (AI Services) account name — globally unique.')
param accountName string

@description('Foundry project name (child of the account).')
param projectName string

@description('Human-readable project description.')
param projectDescription string = 'Enterprise GenAI Platform — primary project'

@description('When true, disables API-key auth — only AAD/MI tokens are accepted.')
param disableLocalAuth bool = true

@description('Array of { name, modelName, modelVersion, skuName, skuCapacity }.')
param deployments array

@description('Principal to grant data-plane access to.')
param principalId string

@description('Principal type.')
param principalType string

param tags object = {}

// ── Built-in role IDs ──────────────────────────────────────────────────────
// "Cognitive Services OpenAI User" — call OpenAI deployments (chat, embeddings)
var openAiUserRoleId = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
// "Azure AI User"  — read project, list models, use playground & non-OpenAI inference
var azureAiUserRoleId = '53ca6127-db72-4b80-b1b0-d745d6d5456d'

// ── Foundry resource (AI Services multi-service account) ───────────────────
resource account 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' = {
  name: accountName
  location: location
  tags: tags
  kind: 'AIServices'                          // ← Foundry (was 'OpenAI')
  sku: {
    name: 'S0'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    customSubDomainName: accountName          // required for AAD/MI auth
    publicNetworkAccess: 'Enabled'            // Phase 1
    disableLocalAuth: disableLocalAuth        // MI-only when true
    allowProjectManagement: true              // ← enables Foundry projects
    networkAcls: {
      defaultAction: 'Allow'
      virtualNetworkRules: []
      ipRules: []
    }
  }
}

// ── Foundry project (child of the account) ─────────────────────────────────
resource project 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' = {
  parent: account
  name: projectName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    description: projectDescription
    displayName: projectName
  }
}

// ── Model deployments (serial — AOAI doesn't allow parallel deploys) ──────
@batchSize(1)
resource modelDeployments 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = [for d in deployments: {
  parent: account
  name: d.name
  sku: {
    name: d.skuName        // 'GlobalStandard' = pay-as-you-go, shared capacity
    capacity: d.skuCapacity // In thousands of TPM (10 = 10K TPM safety ceiling)
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: d.modelName
      version: d.modelVersion
    }
    raiPolicyName: 'Microsoft.DefaultV2'
    versionUpgradeOption: 'OnceCurrentVersionExpired'
  }
}]

// ── RBAC: data-plane (OpenAI calls) ────────────────────────────────────────
resource openAiUserAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(account.id, principalId, openAiUserRoleId)
  scope: account
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      openAiUserRoleId
    )
    principalId: principalId
    principalType: principalType
  }
}

// ── RBAC: project access (Foundry portal, playground, model catalog) ──────
resource azureAiUserAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(project.id, principalId, azureAiUserRoleId)
  scope: project
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      azureAiUserRoleId
    )
    principalId: principalId
    principalType: principalType
  }
}

// ── Outputs ────────────────────────────────────────────────────────────────
output accountName string = account.name
output projectName string = project.name
// Canonical OpenAI sub-endpoint used by the openai SDK. Both this and the
// account.properties.endpoint (".cognitiveservices.azure.com/") resolve to
// the same backend, but ".openai.azure.com/" matches every Microsoft sample
// and avoids confusion.
output endpoint string = 'https://${account.name}.openai.azure.com/'
output projectEndpoint string = 'https://${account.name}.services.ai.azure.com/api/projects/${project.name}'
output foundryPortalUrl string = 'https://ai.azure.com/build/overview?wsid=${project.id}&tid=${subscription().tenantId}'
output deploymentNames array = [for (d, i) in deployments: modelDeployments[i].name]

