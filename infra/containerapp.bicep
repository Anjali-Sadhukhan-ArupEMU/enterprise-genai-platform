// ─────────────────────────────────────────────────────────────────────────────
// Backend host: Azure Container Apps (replaces Azure Functions Flex Consumption)
//
// Why: the Functions ASGI bridge (func.AsgiFunctionApp) BUFFERS the whole
// FastAPI response and flushes once, so SSE token streaming arrives "all at
// once". Container Apps runs the same uvicorn image (Dockerfile) and streams
// each `yield` immediately — true end-to-end SSE.
//
// Scope: resource group (deployed via infra/deploy-containerapp.ps1 with
//        `az deployment group create`). Reuses the existing Log Analytics
//        workspace and Azure OpenAI account already in the RG.
//
// Auth model: a user-assigned managed identity (UAMI) is created FIRST, so its
// principalId is known before the app — no role-assignment race. The UAMI gets:
//   - AcrPull on the container registry (so the app can pull its image)
//   - Cognitive Services OpenAI User on the AOAI account (data-plane token)
// The app sets AZURE_CLIENT_ID=<uami clientId> so DefaultAzureCredential in the
// backend resolves to this UAMI.
// ─────────────────────────────────────────────────────────────────────────────

targetScope = 'resourceGroup'

@description('Azure region. Use the same region as the rest of the RG.')
param location string = resourceGroup().location

@description('Short environment tag — used in resource names and tags.')
@allowed([ 'dev', 'test', 'prod' ])
param environment string = 'dev'

@description('Container Registry name (alphanumeric, globally unique). Created by deploy-containerapp.ps1 before this template runs.')
param acrName string

@description('Full container image reference, e.g. <acr>.azurecr.io/genai-backend:<tag>.')
param containerImage string

@description('Existing Azure OpenAI (Cognitive Services) account name in this RG.')
param openAiAccountName string

@description('Existing Log Analytics workspace name in this RG (reused for the Container Apps environment).')
param logAnalyticsWorkspaceName string

// ── App configuration (mirrors the Function App settings) ──────────────────
@description('Azure OpenAI endpoint (https://<acct>.openai.azure.com/).')
param azureOpenAiEndpoint string

@description('Azure OpenAI deployment name.')
param azureOpenAiDeployment string

@description('Foundry project endpoint.')
param foundryProjectEndpoint string = ''

@description('Allowed CORS origins as a JSON array string.')
param allowedOrigins string

@description('Entra ID tenant ID used to validate bearer tokens.')
param entraTenantId string = ''

@description('Entra ID application (client) ID used as the token audience.')
param entraClientId string = ''

@description('Enable verbose debug mode on the backend.')
param debug bool = false

@description('Master switch for the in-app usage dashboard.')
param usageDashboardEnabled bool = false

@description('Provision an Azure Cosmos DB account and grant the backend UAMI data-plane access. When true, COSMOS_ENDPOINT is injected so conversations + admin config persist to Cosmos instead of in-memory.')
param enableCosmos bool = true

@description('Application Insights connection string (stored as a secret).')
@secure()
param appInsightsConnectionString string = ''

@description('Minimum replicas. Set 0 for scale-to-zero (cheaper, cold starts); 1 keeps it warm.')
@minValue(0)
@maxValue(10)
param minReplicas int = 1

@description('Maximum replicas for HTTP autoscale.')
@minValue(1)
@maxValue(30)
param maxReplicas int = 3

param tags object = {
  project: 'enterprise-genai-platform'
  environment: environment
  managedBy: 'bicep'
  component: 'backend-containerapp'
}

// Built-in role definition ids
var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'
var openAiUserRoleId = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'

var containerAppName = 'ca-genai-${environment}'
var environmentName = 'cae-genai-${environment}'
var uamiName = 'id-genai-backend-${environment}'

// ── User-assigned managed identity (created first; no role-assignment race) ─
resource uami 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: uamiName
  location: location
  tags: tags
}

// ── Existing resources referenced (not created here) ───────────────────────
resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: acrName
}

resource openAi 'Microsoft.CognitiveServices/accounts@2023-05-01' existing = {
  name: openAiAccountName
}

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' existing = {
  name: logAnalyticsWorkspaceName
}

// ── RBAC: UAMI can pull from ACR ───────────────────────────────────────────
resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, uami.id, acrPullRoleId)
  scope: acr
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
    principalId: uami.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// ── RBAC: UAMI can call Azure OpenAI data plane ────────────────────────────
resource openAiUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(openAi.id, uami.id, openAiUserRoleId)
  scope: openAi
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', openAiUserRoleId)
    principalId: uami.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// ── Cosmos DB (conversations + admin config) with data-plane RBAC for UAMI ──
module cosmos 'cosmos.bicep' = if (enableCosmos) {
  name: 'cosmos-${environment}'
  params: {
    location: location
    environment: environment
    dataContributorPrincipalId: uami.properties.principalId
    tags: tags
  }
}

// ── Container Apps managed environment (wired to existing Log Analytics) ────
resource managedEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: environmentName
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

// ── The Container App ──────────────────────────────────────────────────────
resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: containerAppName
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${uami.id}': {}
    }
  }
  properties: {
    managedEnvironmentId: managedEnv.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
        allowInsecure: false
        traffic: [
          {
            latestRevision: true
            weight: 100
          }
        ]
      }
      registries: [
        {
          server: acr.properties.loginServer
          identity: uami.id
        }
      ]
      secrets: empty(appInsightsConnectionString) ? [] : [
        {
          name: 'appinsights-connection-string'
          value: appInsightsConnectionString
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'backend'
          image: containerImage
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: concat([
            {
              name: 'AZURE_CLIENT_ID'
              value: uami.properties.clientId
            }
            {
              name: 'AZURE_OPENAI_ENDPOINT'
              value: azureOpenAiEndpoint
            }
            {
              name: 'AZURE_OPENAI_DEPLOYMENT'
              value: azureOpenAiDeployment
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
              value: allowedOrigins
            }
            {
              name: 'ENTRA_TENANT_ID'
              value: entraTenantId
            }
            {
              name: 'ENTRA_CLIENT_ID'
              value: entraClientId
            }
            {
              name: 'DEBUG'
              value: string(debug)
            }
            {
              name: 'USAGE_DASHBOARD_ENABLED'
              value: string(usageDashboardEnabled)
            }
            {
              name: 'ROUTING_CONFIG_PATH'
              value: 'config/routing_config.json'
            }
            {
              name: 'LOG_LOCAL_DIR'
              value: '/tmp/genai-logs'
            }
          ], enableCosmos ? [
            {
              name: 'COSMOS_ENDPOINT'
              value: cosmos.outputs.documentEndpoint
            }
          ] : [], empty(appInsightsConnectionString) ? [] : [
            {
              name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
              secretRef: 'appinsights-connection-string'
            }
          ])
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
        rules: [
          {
            name: 'http-scale'
            http: {
              metadata: {
                concurrentRequests: '50'
              }
            }
          }
        ]
      }
    }
  }
  dependsOn: [
    acrPull
  ]
}

output containerAppFqdn string = containerApp.properties.configuration.ingress.fqdn
output containerAppUrl string = 'https://${containerApp.properties.configuration.ingress.fqdn}'
output containerAppName string = containerApp.name
output uamiClientId string = uami.properties.clientId
output uamiPrincipalId string = uami.properties.principalId
output cosmosAccountName string = enableCosmos ? cosmos.outputs.accountName : ''
output cosmosEndpoint string = enableCosmos ? cosmos.outputs.documentEndpoint : ''
output acrLoginServer string = acr.properties.loginServer
