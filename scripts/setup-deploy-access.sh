#!/usr/bin/env bash
# One-time setup of what the deploy pipeline needs to reach the server.
#
# Run it from a machine that can already SSH to the server as root and has the GitHub
# CLI logged in:
#
#   bash scripts/setup-deploy-access.sh
#
# What it does:
#   1. makes a key pair for the pipeline (its own, not a person's key)
#   2. puts the public half in the server's authorized_keys
#   3. stores the private half as the repository secret SSH_PRIVATE_KEY
#   4. creates the GitHub environment "production", open to runs from main only,
#      and gives it a generated POSTGRES_PASSWORD
#   5. deletes the local copy of the private half, also when a step fails: after this
#      it exists only at GitHub
#
# Running it again makes a new key pair and adds its public half to the server. The old
# public half stays in authorized_keys until it is removed there by hand. A database
# password that already exists is kept, because the database was created with it.

set -euo pipefail

REPO="Arvid-Borglund/gn-take-home"
HOST="135.181.92.165"

WORK_DIR="$(mktemp -d)"
KEY="$WORK_DIR/deploy_key"

# Whatever happens below, the private half does not stay on this machine.
trap 'rm -rf "$WORK_DIR"' EXIT

echo "1. Making a key pair for the pipeline"
ssh-keygen -q -t ed25519 -N "" -C "gn-take-home-deploy" -f "$KEY"

echo "2. Putting the public half on the server"
ssh-copy-id -i "$KEY.pub" "root@$HOST"

echo "3. Storing the private half as the secret SSH_PRIVATE_KEY"
gh secret set SSH_PRIVATE_KEY --repo "$REPO" < "$KEY"

echo "4. Creating the environment production"
gh api -X PUT "repos/$REPO/environments/production" --silent --input - <<'JSON'
{"deployment_branch_policy": {"protected_branches": false, "custom_branch_policies": true}}
JSON
# Fails when the rule is already there, which is fine.
gh api -X POST "repos/$REPO/environments/production/deployment-branch-policies" \
  --silent -f name=main -f type=branch || true

if gh secret list --repo "$REPO" --env production | grep -q "^POSTGRES_PASSWORD"; then
  echo "   POSTGRES_PASSWORD already exists and is kept"
else
  gh secret set POSTGRES_PASSWORD --repo "$REPO" --env production --body "$(openssl rand -hex 24)"
fi

echo "5. The local copy of the private half is deleted when the script ends"

echo
echo "Done. Start the first deploy with:"
echo "  gh workflow run deploy.yml --repo $REPO -f bootstrap=true"
