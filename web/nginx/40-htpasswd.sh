#!/bin/sh
# Writes the password file when the container starts, if the site is protected.
#
# Run by the nginx image's entrypoint (/docker-entrypoint.d/, in file name order, after
# the templates and before nginx starts).
#
# The password is never in the repository. BASIC_AUTH_HTPASSWD is a secret and holds
# finished htpasswd lines, "user:hash", one line per user. Make a line with:
#
#   docker run --rm httpd:alpine htpasswd -nbB <user> '<password>'
#
# Kamal passes the value through Docker's env file, which is line based, and writes
# every line break in it as the two characters \n. %b in printf below turns them back
# into line breaks. A value with a single line is not affected.
set -e

if [ "${SITE_PRIVATE:-off}" != "on" ]; then
  exit 0
fi

if [ -z "${BASIC_AUTH_HTPASSWD:-}" ]; then
  echo "ERROR: SITE_PRIVATE=on but BASIC_AUTH_HTPASSWD is empty." >&2
  echo "Refusing to start rather than serve the site without a password." >&2
  exit 1
fi

printf '%b\n' "$BASIC_AUTH_HTPASSWD" > /etc/nginx/private/htpasswd

# The entrypoint runs as root, but nginx's worker processes run as the user "nginx",
# and they are the ones that read the file. Owned by root with mode 600 the result is
# HTTP 500, not 401, which looks like a wrong password but is a permission error.
chown nginx:nginx /etc/nginx/private/htpasswd
chmod 400 /etc/nginx/private/htpasswd

echo "SITE_PRIVATE=on: basic auth is active"
