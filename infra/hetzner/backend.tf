# Remote state in Cloudflare R2, which speaks the S3 protocol.
#
# Without a remote backend the state is a file on the machine that ran Terraform. If
# that file is lost, Terraform no longer knows which servers it created, and the next
# apply wants to create them again next to the existing ones.
#
# R2 and not Hetzner's own object storage, for two reasons: R2 has no fixed monthly fee,
# and the state then lives with another provider than the servers it describes.
#
# What belongs to the account is not written here. It is given at init:
#
#   bucket       terraform init -backend-config="bucket=<name>"
#   endpoint     the environment variable AWS_ENDPOINT_URL_S3
#   credentials  AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY (the R2 keys; the names
#                are AWS's because the backend is the S3 one)
#
# To check the files without any of that:  terraform init -backend=false

terraform {
  backend "s3" {
    key = "gn-take-home/terraform.tfstate"

    # R2 has no regions in the AWS sense.
    region = "auto"

    # R2 is not AWS. Without these Terraform tries to validate the region, the account
    # id and the instance metadata against AWS, and fails.
    skip_credentials_validation = true
    skip_region_validation      = true
    skip_requesting_account_id  = true
    skip_metadata_api_check     = true
    skip_s3_checksum            = true
    use_path_style              = true

    # A lock file in the bucket stops two applies from running at the same time.
    use_lockfile = true
  }
}
