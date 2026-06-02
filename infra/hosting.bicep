// ─────────────────────────────────────────────────────────────────────────────
// Enterprise GenAI Platform — hosting (frontend + backend)
// Scope: resource group (deploy INTO the existing rg-genai-dev)
//
// Creates:
//   - Storage account            (Functions Flex deployment + AzureWebJobsStorage)
//   - Log Analytics + App Insights (telemetry)
//   - Flex Consumption plan (FC1) (HTTP response streaming → SSE preserved)
//   - Linux Function App           (system-assigned MI; runs the FastAPI ASGI app)
//   - Static Web App (Free)        (React/Vite frontend)
//   - RBAC: Function MI → Cognitive Services OpenAI User on the existing AOAI acct
//   - RBAC: Function MI → Storage Blob Data Owner on the new storage account
//
// Run:
//   az deployment group create `
//     --resource-group rg-genai-dev `
//     --template-file infra/hosting.bicep `
//     --parameters openAiAccountName=aoai-genai-dev-oc2nlehve57q4 `
//                  openAiDeployment=gpt-4o-mini-test
// ─────────────────────────────────────────────────────────────────────────────

targetScope = 'resourceGroup'

@description('Azure region. East US 2 supports Flex Consumption + Static Web Apps.')
param location string = resourceGroup().location

@description('Short environment tag used in resource names.')
param environment string = 'prod'

@description('Name of the EXISTING Azure OpenAI account in this resource group (for RBAC).')
param openAiAccountName string

@description('Azure OpenAI endpoint (https://<acct>.openai.azure.com/).')
param openAiEndpoint string = 'https://${openAiAccountName}.openai.azure.com/'

@description('Azure OpenAI deployment name the backend should target.')
param openAiDeployment string = 'gpt-4o-mini-test'

@description('Foundry project endpoint (optional, for non-OpenAI Foundry models).')
param foundryProjectEndpoint string = ''

@description('Globally-unique-ish suffix for resource names.')
param nameSuffix string = uniqueString(resourceGroup().id, environment)

@description('Function App name (becomes <name>.azurewebsites.net).')
param functionAppName string = 'func-genai-${environment}-${nameSuffix}'

@description('Static Web App name.')
param staticWebAppName string = 'swa-genai-${environment}-${nameSuffix}'

@description('Storage account name (3-24 lowercase alphanumerics).')
param storageAccountName string = toLower('stgenai${environment}${take(nameSuffix, 10)}')

param tags object = {
  project: 'enterprise-genai-platform'
  environment: environment
  managedBy: 'bicep'
}

// Built-in role definition IDs
var roleOpenAiUser = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd') // Cognitive Services OpenAI User
var roleBlobOwner = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b') // Storage Blob Data Owner

var deployContainerName = 'app-package'

// ── Existing Azure OpenAI account (for role assignment) ─────────────────────
resource openAi 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = {
  name: openAiAccountName
}

// ── Storage account ─────────────────────────────────────────────────────────
resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
  location: location
  tags: tags
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: true
    supportsHttpsTrafficOnly: true
  }
}

resource blobServices 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
}

resource deployContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobServices
  name: deployContainerName
  properties: {
    publicAccess: 'None'
  }
}

// ── Log Analytics + Application Insights ────────────────────────────────────
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-genai-${environment}-${nameSuffix}'
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-genai-${environment}-${nameSuffix}'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
  }
}

// ── Flex Consumption plan ───────────────────────────────────────────────────
resource plan 'Microsoft.Web/serverfarms@2024-04-01' = {
  name: 'plan-genai-${environment}-${nameSuffix}'
  location: location
  tags: tags
  kind: 'functionapp'
  sku: {
    tier: 'FlexConsumption'
    name: 'FC1'
  }
  properties: {
    reserved: true
  }
}

// ── Function App (Flex Consumption, Linux, Python 3.12) ─────────────────────
resource functionApp 'Microsoft.Web/sites@2024-04-01' = {
  name: functionAppName
  location: location
  tags: tags
  kind: 'functionapp,linux'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    functionAppConfig: {
      deployment: {
        storage: {
          type: 'blobContainer'
          value: '${storage.properties.primaryEndpoints.blob}${deployContainerName}'
          authentication: {
            type: 'SystemAssignedIdentity'
          }
        }
      }
      scaleAndConcurrency: {
        maximumInstanceCount: 40
        instanceMemoryMB: 2048
      }
      runtime: {
        name: 'python'
        version: '3.12'
      }
    }
    siteConfig: {
      minTlsVersion: '1.2'
      cors: {
        allowedOrigins: [
          'https://${staticWebApp.properties.defaultHostname}'
          'http://localhost:3000'
        ]
        supportCredentials: false
      }
      appSettings: [
        {
          name: 'AzureWebJobsStorage__accountName'
          value: storage.name
        }
        {
          name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
          value: appInsights.properties.ConnectionString
        }
        {
          name: 'AZURE_OPENAI_ENDPOINT'
          value: openAiEndpoint
        }
        {
          name: 'AZURE_OPENAI_DEPLOYMENT'
          value: openAiDeployment
        }
        {
          name: 'AZURE_OPENAI_USE_MANAGED_IDENTITY'
          value: 'true'
        }
        {
          name: 'FOUNDRY_PROJECT_ENDPOINT'
          value: foundryProjectEndpoint
        }
        {
          name: 'ALLOWED_ORIGINS'
          value: '["https://${staticWebApp.properties.defaultHostname}","http://localhost:3000"]'
        }
        {
          name: 'DEBUG'
          value: 'false'
        }
        {
          name: 'ROUTING_CONFIG_PATH'
          value: 'config/routing_config.json'
        }
        {
          name: 'USAGE_DASHBOARD_ENABLED'
          value: 'false'
        }
        {
          // Flex package mount (/home/site/wwwroot) is read-only; write
          // audit/usage/feedback jsonl to the writable temp dir instead.
          name: 'LOG_LOCAL_DIR'
          value: '/tmp/genai-logs'
        }
      ]
    }
  }
}

// ── Static Web App (Free) ───────────────────────────────────────────────────
resource staticWebApp 'Microsoft.Web/staticSites@2024-04-01' = {
  name: staticWebAppName
  location: location
  tags: tags
  sku: {
    tier: 'Free'
    name: 'Free'
  }
  properties: {
    // Deployment happens via GitHub Actions using the deployment token;
    // no repository wiring is configured here.
  }
}

// ── RBAC: Function MI → Cognitive Services OpenAI User on AOAI ──────────────
resource openAiRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(openAi.id, functionApp.id, roleOpenAiUser)
  scope: openAi
  properties: {
    principalId: functionApp.identity.principalId
    roleDefinitionId: roleOpenAiUser
    principalType: 'ServicePrincipal'
  }
}

// ── RBAC: Function MI → Storage Blob Data Owner (deployment + AzureWebJobs) ─
resource storageRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, functionApp.id, roleBlobOwner)
  scope: storage
  properties: {
    principalId: functionApp.identity.principalId
    roleDefinitionId: roleBlobOwner
    principalType: 'ServicePrincipal'
  }
}

// ── Outputs ─────────────────────────────────────────────────────────────────
output functionAppName string = functionApp.name
output functionAppUrl string = 'https://${functionApp.properties.defaultHostName}'
output staticWebAppName string = staticWebApp.name
output staticWebAppUrl string = 'https://${staticWebApp.properties.defaultHostname}'
output storageAccountName string = storage.name
output appInsightsName string = appInsights.name
