terraform {
  # 1.10 is needed for the lock file in the S3 backend (use_lockfile in backend.tf).
  required_version = ">= 1.10"

  required_providers {
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = ">= 1.45"
    }
  }
}

# The API token is read from the environment variable HCLOUD_TOKEN.
# No token in code, and none in files next to the state.
provider "hcloud" {}
