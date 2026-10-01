# The server the API is deployed on, at Hetzner: the machine, its reserved address,
# the firewall in front of it and the SSH key it was created with.
#
# Terraform owns the machine. What runs on it is Kamal's job (config/deploy.yml).
#
# The server already existed when this file was written, so nothing here was created
# by this configuration. The import blocks at the bottom adopt the three resources into
# the state instead. After that, "terraform plan" answers one question: does the
# machine still look like this file says? An empty plan means yes.

# The SSH key is a person's key that is registered at Hetzner, not something that
# belongs to this server. It is looked up by name instead of being managed here.
data "hcloud_ssh_key" "admin" {
  name = var.ssh_key_name
}

# 22 for SSH (the deploy runs over it), 80 and 443 for kamal-proxy. PostgreSQL's 5432
# is not here on purpose: the database is reached over Docker's network on the server,
# never from outside.
resource "hcloud_firewall" "web" {
  name = "tenderiq-web"

  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "22"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "80"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "443"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  rule {
    direction  = "in"
    protocol   = "icmp"
    source_ips = ["0.0.0.0/0", "::/0"]
  }
}

# The public address is a resource of its own, so that it outlives the server. DNS
# points at it: if the address went away with a rebuilt machine, the A records would
# be wrong without any error telling why.
resource "hcloud_primary_ip" "host_ipv4" {
  name          = "tenderiq-prod-ipv4"
  type          = "ipv4"
  assignee_type = "server"
  assignee_id   = hcloud_server.host.id

  auto_delete       = false
  delete_protection = true

  labels = {
    project = "tenderiq"
    env     = "production"
  }
}

resource "hcloud_server" "host" {
  name         = "tenderiq-prod"
  server_type  = var.server_type
  image        = "ubuntu-24.04"
  location     = var.location
  ssh_keys     = [data.hcloud_ssh_key.admin.id]
  firewall_ids = [hcloud_firewall.web.id]

  # Hetzner's own backup: a daily image of the whole machine, seven kept. It saves the
  # server. The database dumps (.github/workflows/backup-db.yml) save the data.
  backups = true

  # These two are stored at Hetzner and hold for every way in: the console, the API,
  # the CLI and Terraform. prevent_destroy below only holds for Terraform.
  delete_protection  = true
  rebuild_protection = true

  labels = {
    project = "tenderiq"
    env     = "production"
  }

  lifecycle {
    prevent_destroy = true

    # Hetzner installs the SSH key when the server is created and does not report it
    # afterwards. For an imported server the value is unknown, and a difference here
    # would mean "replace the server".
    ignore_changes = [ssh_keys]
  }
}

# ----- Adoption of what already exists -----

import {
  to = hcloud_firewall.web
  id = "11445925"
}

import {
  to = hcloud_server.host
  id = "161627049"
}

import {
  to = hcloud_primary_ip.host_ipv4
  id = "144460358"
}
