variable "location" {
  description = "Hetzner data centre. hel1 is Helsinki."
  type        = string
  default     = "hel1"
}

variable "server_type" {
  description = "Hetzner plan. cx33 is 4 shared vCPU, 8 GB of memory and 80 GB of disk."
  type        = string
  default     = "cx33"
}

variable "ssh_key_name" {
  description = "Name, at Hetzner, of the SSH key the server was created with."
  type        = string
  default     = "arvid-laptop"
}
