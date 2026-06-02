// ─────────────────────────────────────────────────────────────────────────────
// Optional: Monthly budget alert for the GenAI test resource group.
// Run separately AFTER the main deployment if you want spend tracking.
//
//   az deployment sub create `
//     --location eastus2 `
//     --template-file infra/budget.bicep `
//     --parameters resourceGroupName=rg-genai-dev `
//                  contactEmails='["asadhukhan@Microsoft.com"]' `
//                  monthlyAmount=8000 currencyCode=INR
// ─────────────────────────────────────────────────────────────────────────────

targetScope = 'subscription'

@description('Resource group to scope the budget to.')
param resourceGroupName string

@description('Monthly cap in the subscription currency (INR here).')
param monthlyAmount int = 8000

@description('Currency code matching the subscription (INR for VS Enterprise India).')
param currencyCode string = 'INR'

@description('Emails that receive alerts at 50% / 80% / 100% / 110% of budget.')
param contactEmails array

@description('Budget name.')
param budgetName string = 'genai-monthly-cap'

// Budgets must start at midnight on day 1 of a month
var startDate = '${utcNow('yyyy-MM')}-01'

resource budget 'Microsoft.Consumption/budgets@2023-11-01' = {
  name: budgetName
  properties: {
    timePeriod: {
      startDate: startDate
    }
    timeGrain: 'Monthly'
    amount: monthlyAmount
    category: 'Cost'
    filter: {
      dimensions: {
        name: 'ResourceGroupName'
        operator: 'In'
        values: [ resourceGroupName ]
      }
    }
    notifications: {
      Actual_50: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 50
        thresholdType: 'Actual'
        contactEmails: contactEmails
      }
      Actual_80: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 80
        thresholdType: 'Actual'
        contactEmails: contactEmails
      }
      Forecasted_100: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 100
        thresholdType: 'Forecasted'
        contactEmails: contactEmails
      }
      Actual_110: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 110
        thresholdType: 'Actual'
        contactEmails: contactEmails
      }
    }
  }
}

output budgetId string = budget.id
