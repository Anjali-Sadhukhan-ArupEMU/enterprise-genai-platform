# Infra (Bicep)

Provisions the Azure resources for the Enterprise GenAI Platform.

## What gets created

| Resource                                   | Purpose                                             | Cost shape                |
| ------------------------------------------ | --------------------------------------------------- | ------------------------- |
| Resource group `rg-genai-<env>`            | Container                                           | $0                        |
| Azure OpenAI account (kind=OpenAI, SKU=S0) | The actual AOAI resource                            | $0 (pay per token)        |
| Deployment `gpt-4o-mini-test`              | Cheap chat model — primary test target              | $0.15/$0.60 per 1M in/out |
| Deployment `gpt-4.1-mini-test`             | Mid-tier for quality compares                       | $0.40/$1.60 per 1M in/out |
| Role assignment                            | "Cognitive Services OpenAI User" → caller principal | $0                        |

Hard ceilings baked into the template:

- `skuCapacity: 10` → **10K TPM per deployment** (the lowest safe cap)
- `disableLocalAuth: true` → API keys refused; only Managed Identity / AAD tokens work
- `customSubDomainName` set → required for AAD auth on data plane

## Files

| File                   | Purpose                                                                                     |
| ---------------------- | ------------------------------------------------------------------------------------------- |
| `main.bicep`           | Subscription-scope entry point. Creates RG, calls module.                                   |
| `openai.bicep`         | RG-scope module: AOAI account + deployments + RBAC.                                         |
| `main.parameters.json` | Default parameter values (env, location, deployment list).                                  |
| `deploy.ps1`           | Wrapper: signs you in, resolves your AAD object id, deploys, writes outputs into `../.env`. |

## Prerequisites

```powershell
# Azure CLI ≥ 2.60 with Bicep
az --version
az bicep upgrade

# Sign in to the subscription holding your VS credit
az login
az account set --subscription "<your-vs-subscription-name-or-id>"
```

## Deploy

```powershell
# Preview (no changes)
.\infra\deploy.ps1 -WhatIf

# For real
.\infra\deploy.ps1

# Different env / region
.\infra\deploy.ps1 -Environment test -Location swedencentral
```

The script will:

1. Resolve your AAD object id (so RBAC lands on you, not the deployment SP)
2. Run `az deployment sub create` against `main.bicep`
3. Read the outputs and **write `AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_DEPLOYMENT` / `AZURE_OPENAI_USE_MANAGED_IDENTITY=true` into `../.env`**
4. Print the next command to restart the backend

## Verify

```powershell
# List the deployments
az cognitiveservices account deployment list `
  -g rg-genai-dev -n <aoai-name> -o table

# Confirm role landed
$SCOPE = az cognitiveservices account show -g rg-genai-dev -n <aoai-name> --query id -o tsv
az role assignment list `
  --assignee (az ad signed-in-user show --query id -o tsv) `
  --scope $SCOPE -o table

# Smoke test
curl -X POST http://localhost:8000/api/v1/chat `
  -H "Content-Type: application/json" `
  -d '{\"message\":\"Say hi in 5 words\",\"mode\":\"quick\"}'
```

## Tear down (when finished testing)

```powershell
# Whole RG — fastest, removes ALL spend
az group delete -n rg-genai-dev --yes --no-wait

# Single deployment only (keeps the AOAI account)
az cognitiveservices account deployment delete `
  -g rg-genai-dev -n <aoai-name> --deployment-name gpt-4.1-mini-test
```

## CI/CD wiring (later)

The same Bicep runs unchanged from GitHub Actions / Azure DevOps:

```yaml
- uses: azure/login@v2
  with:
    client-id: ${{ secrets.AZURE_CLIENT_ID }}
    tenant-id: ${{ secrets.AZURE_TENANT_ID }}
    subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
- run: |
    az deployment sub create \
      --location eastus2 \
      --template-file infra/main.bicep \
      --parameters infra/main.parameters.json \
      --parameters principalId=${{ secrets.APP_PRINCIPAL_ID }}
```

In CI, pass the **App Service / Container App MI principalId** instead of your user — so the _app_ gets the role, not a human.

## Future modules to add (Phase 2+)

Drop new files next to `openai.bicep` and call them from `main.bicep`:

- `cosmos.bicep` — Cosmos DB with SQL API + RBAC for app MI
- `storage.bicep` — ADLS Gen2 account for audit logs
- `keyvault.bicep` — KV with RBAC role for `Key Vault Secrets User`
- `appservice.bicep` or `containerapp.bicep` — host the FastAPI app, attach system MI, assign all the data-plane roles
- `apim.bicep` — API Management gateway in front of the app (for JWT validation per architecture spec)
