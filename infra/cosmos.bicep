// ─────────────────────────────────────────────────────────────────────────────
// Azure Cosmos DB (SQL/Core API) — persistence for conversations + admin config.
//
// Designed to be used as a MODULE from infra/containerapp.bicep so the backend's
// user-assigned managed identity (UAMI) principalId is known and can be granted
// data-plane access in the same deployment (no role-assignment race).
//
// What it creates:
//   - A serverless Cosmos account (SQL API), local auth DISABLED (MI/RBAC only)
//   - Database `genai_platform`
//   - Container `conversations`  (partition key /user_id)  → chat history
//   - Container `admin_config`   (partition key /id)        → admin settings doc
//   - A SQL data-plane role assignment granting the UAMI the built-in
//     "Cosmos DB Built-in Data Contributor" role (read/write items).
//
// Why serverless: low, spiky admin/chat traffic — pay-per-RU is cheaper than
// provisioned throughput for this workload and needs no capacity planning.
// ─────────────────────────────────────────────────────────────────────────────

targetScope = 'resourceGroup'

@description('Azure region. Use the same region as the rest of the RG.')
param location string = resourceGroup().location

@description('Short environment tag — used in resource names and tags.')
@allowed([ 'dev', 'test', 'prod' ])
param environment string = 'dev'

@description('Globally-unique Cosmos account name (lowercase, 3-44 chars).')
param accountName string = toLower('cosmos-genai-${environment}-${uniqueString(resourceGroup().id)}')

@description('SQL database name.')
param databaseName string = 'genai_platform'

@description('Conversations container name (chat history).')
param conversationsContainerName string = 'conversations'

@description('Admin config container name (single settings doc).')
param adminConfigContainerName string = 'admin_config'

@description('Principal ID (UAMI) to grant data-plane read/write. Leave empty to skip the role assignment.')
param dataContributorPrincipalId string = ''

param tags object = {
  project: 'enterprise-genai-platform'
  environment: environment
  managedBy: 'bicep'
  component: 'cosmos'
}

// Built-in Cosmos DB SQL data-plane role: "Cosmos DB Built-in Data Contributor".
// This is a FIXED, well-known role-definition GUID for every account.
var dataContributorRoleId = '00000000-0000-0000-0000-000000000002'

// ── Cosmos account (SQL API, serverless, MI-only auth) ──────────────────────
resource account 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' = {
  name: accountName
  location: location
  tags: tags
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    // RBAC/Managed Identity only — no account keys/connection strings used.
    disableLocalAuth: true
    enableAutomaticFailover: false
    consistencyPolicy: {
      defaultConsistencyLevel: 'Session'
    }
    locations: [
      {
        locationName: location
        failoverPriority: 0
        isZoneRedundant: false
      }
    ]
    capabilities: [
      {
        name: 'EnableServerless'
      }
    ]
  }
}

// ── Database ────────────────────────────────────────────────────────────────
resource database 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-05-15' = {
  parent: account
  name: databaseName
  properties: {
    resource: {
      id: databaseName
    }
  }
}

// ── Container: conversations (partition /user_id) ───────────────────────────
resource conversations 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: database
  name: conversationsContainerName
  properties: {
    resource: {
      id: conversationsContainerName
      partitionKey: {
        paths: [ '/user_id' ]
        kind: 'Hash'
      }
    }
  }
}

// ── Container: admin_config (partition /id — single "admin_config" doc) ──────
resource adminConfig 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: database
  name: adminConfigContainerName
  properties: {
    resource: {
      id: adminConfigContainerName
      partitionKey: {
        paths: [ '/id' ]
        kind: 'Hash'
      }
    }
  }
}

// ── Data-plane RBAC: grant the UAMI read/write on this account ───────────────
resource dataContributor 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-05-15' = if (!empty(dataContributorPrincipalId)) {
  parent: account
  name: guid(account.id, dataContributorPrincipalId, dataContributorRoleId)
  properties: {
    roleDefinitionId: '${account.id}/sqlRoleDefinitions/${dataContributorRoleId}'
    principalId: dataContributorPrincipalId
    scope: account.id
  }
}

output accountName string = account.name
output documentEndpoint string = account.properties.documentEndpoint
output databaseName string = databaseName
