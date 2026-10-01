variable "project_name" {
  description = "Short name that goes into every resource name."
  type        = string
  default     = "ticketing"
}

variable "environment" {
  description = "The environment the resources belong to, for example dev or prod."
  type        = string
  default     = "dev"
}

variable "location" {
  description = "Azure region for all resources."
  type        = string
  default     = "swedencentral"
}

variable "sku_name" {
  description = "Size of the App Service plan."
  type        = string
  default     = "B1"
}

variable "api_image" {
  description = "Container image of the ticket API with its tag, without the registry address."
  type        = string
  default     = "arvid-borglund/gn-take-home/api:latest"
}

variable "database_connection_string" {
  description = "Connection string to the PostgreSQL database the API uses. Placeholder by default."
  type        = string
  sensitive   = true
  default     = "Host=placeholder;Port=5432;Database=ticketdb;Username=ticket;Password=placeholder"
}
