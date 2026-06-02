// ─────────────────────────────────────────────────────────────────────────────
// Grounding with Bing Search — resource + Foundry project connection
// Scope: resource group (called from main.bicep AFTER the openai module)
//
// Shape:
//   Microsoft.Bing/accounts  (kind: Bing.Grounding, sku: G1)        ← billed per call
//     └── referenced by a project connection so the agents SDK can use it:
//   Microsoft.CognitiveServices/accounts/<acct>/projects/<proj>/connections/<name>
//       (category: GroundingWithBingSearch)
//
// The connection's resourceId is what the app passes as
// BING_GROUNDING_CONNECTION_ID; the project endpoint is BING_GROUNDING_ENDPOINT.
//
// Prereq: the Microsoft.Bing resource provider must be registered on the sub
//   az provider register --namespace Microsoft.Bing
// Note: Grounding with Bing data leaves the Azure compliance boundary (Bing
//   terms apply). Review with governance before enabling in prod.
// ─────────────────────────────────────────────────────────────────────────────

@description('Existing Foundry (AI Services) account name.')
param accountName string

@description('Existing Foundry project name (child of the account).')
param projectName string

@description('Bing Grounding account name — globally unique.')
param bingAccountName string

@description('Name of the project connection that wraps the Bing account.')
param connectionName string = 'bing-grounding'

param tags object = {}

// ── Bing Grounding account (always "global") ────────────────────────────────
resource bingAccount 'Microsoft.Bing/accounts@2020-06-10' = {
  name: bingAccountName
  location: 'global'
  kind: 'Bing.Grounding'
  sku: {
    name: 'G1'
  }
  tags: tags
}

// ── Existing Foundry account + project (created by openai.bicep) ───────────
resource account 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
  name: accountName
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' existing = {
  parent: account
  name: projectName
}

// ── Project connection: Grounding with Bing Search ─────────────────────────
resource bingConnection 'Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview' = {
  parent: project
  name: connectionName
  properties: {
    category: 'GroundingWithBingSearch'
    target: 'https://api.bing.microsoft.com/'
    authType: 'ApiKey'
    isSharedToAll: true
    credentials: {
      key: bingAccount.listKeys().key1
    }
    metadata: {
      ApiType: 'Azure'
      ResourceId: bingAccount.id
      location: bingAccount.location
    }
  }
}

// ── Outputs ────────────────────────────────────────────────────────────────
output bingAccountName string = bingAccount.name
output connectionName string = bingConnection.name
// Full ARM resource id — what the agents SDK BingGroundingTool needs.
output connectionId string = bingConnection.id
