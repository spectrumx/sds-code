#!/bin/bash

if [ -z "$OPENSEARCH_INITIAL_ADMIN_PASSWORD" ]; then
    echo "Error: OPENSEARCH_INITIAL_ADMIN_PASSWORD must be set"
    exit 1
fi

if [ -z "$OPENSEARCH_USER" ] || [ -z "$OPENSEARCH_PASSWORD" ]; then
    echo "Error: OPENSEARCH_USER and OPENSEARCH_PASSWORD must be set"
    exit 1
fi

# Wait for OpenSearch to start by checking the port
until nc -z localhost 9200; do
    echo 'Waiting for OpenSearch port to be available...'
    sleep 3
done

echo "OpenSearch port is available - waiting a bit more for full startup..."
sleep 5

# Generate password hashes first
ADMIN_HASH=$(/usr/share/opensearch/plugins/opensearch-security/tools/hash.sh -p "$OPENSEARCH_INITIAL_ADMIN_PASSWORD" | tail -n 1)
CLIENT_HASH=$(/usr/share/opensearch/plugins/opensearch-security/tools/hash.sh -p "$OPENSEARCH_PASSWORD" | tail -n 1)

# Export the hashes so they can be used by envsubst
export ADMIN_HASH
export CLIENT_HASH

CONFIG_DIR="/usr/share/opensearch/config/opensearch-security"

# Do variable substitution in place for internal_users.yml
envsubst '${ADMIN_HASH} ${CLIENT_HASH} ${OPENSEARCH_USER}' < "$CONFIG_DIR/internal_users.yml" > "$CONFIG_DIR/internal_users.yml.tmp" && \
mv "$CONFIG_DIR/internal_users.yml.tmp" "$CONFIG_DIR/internal_users.yml"

# Do variable substitution in place for roles_mapping.yml
envsubst '${OPENSEARCH_USER}' < "$CONFIG_DIR/roles_mapping.yml" > "$CONFIG_DIR/roles_mapping.yml.tmp" && \
mv "$CONFIG_DIR/roles_mapping.yml.tmp" "$CONFIG_DIR/roles_mapping.yml"

echo "Applying security configuration..."

# Run security admin script with admin certificates
/usr/share/opensearch/plugins/opensearch-security/tools/securityadmin.sh \
    -cd /usr/share/opensearch/config/opensearch-security/ \
    -icl -nhnv \
    -cacert /usr/share/opensearch/config/certs/root-ca.pem \
    -cert /usr/share/opensearch/config/certs/admin.pem \
    -key /usr/share/opensearch/config/certs/admin-key.pem

echo "Security configuration completed"
