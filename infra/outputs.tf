output "api_url" {
  description = "Address of the deployed ticket API."
  value       = "https://${azurerm_linux_web_app.api.default_hostname}"
}

output "resource_group_name" {
  description = "The resource group everything is created in."
  value       = azurerm_resource_group.ticketing.name
}
