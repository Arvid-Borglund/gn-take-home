# How the ticket API would run on Azure: as a container in App Service.
#
#   resource group  ->  App Service plan (the machine)  ->  Web App (the API container)
#
# Nothing here is applied; the files only have to pass "terraform validate".
#
# The API needs a PostgreSQL database. It is left out on purpose, since the task asks
# for the minimum: the connection string comes in as a variable. In a real setup the
# database would be an azurerm_postgresql_flexible_server in this file.

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}

# The subscription is not written here. Terraform reads it from the environment
# variable ARM_SUBSCRIPTION_ID when a plan or an apply runs.
provider "azurerm" {
  features {}
}

resource "azurerm_resource_group" "ticketing" {
  name     = "rg-${var.project_name}-${var.environment}"
  location = var.location
}

resource "azurerm_service_plan" "ticketing" {
  name                = "asp-${var.project_name}-${var.environment}"
  resource_group_name = azurerm_resource_group.ticketing.name
  location            = azurerm_resource_group.ticketing.location
  os_type             = "Linux"
  sku_name            = var.sku_name
}

resource "azurerm_linux_web_app" "api" {
  # The name becomes part of the address (<name>.azurewebsites.net), so it has to be
  # unique in all of Azure.
  name                = "app-${var.project_name}-api-${var.environment}"
  resource_group_name = azurerm_resource_group.ticketing.name
  location            = azurerm_service_plan.ticketing.location
  service_plan_id     = azurerm_service_plan.ticketing.id
  https_only          = true

  site_config {
    application_stack {
      docker_registry_url = "https://ghcr.io"
      docker_image_name   = var.api_image
    }
  }

  app_settings = {
    # The port the API listens on inside the container.
    WEBSITES_PORT = "8080"

    # ASP.NET reads this as ConnectionStrings:TicketDb, the same setting compose.yaml
    # passes to the container locally.
    ConnectionStrings__TicketDb = var.database_connection_string
  }
}
