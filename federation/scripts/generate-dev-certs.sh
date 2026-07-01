#!/usr/bin/env bash
# Generate a local dev PKI for federation mTLS experiments.
#
# Documentation: docs/mtls-certificates.md
#
# Output directory defaults to federation/certs/ (mounted at /etc/sds/certs in compose).
#
# Usage:
#   ./scripts/generate-dev-certs.sh all
#   ./scripts/generate-dev-certs.sh ca
#   ./scripts/generate-dev-certs.sh client --site-name crc
#   ./scripts/generate-dev-certs.sh server --server-cn localhost --dns localhost --ip 127.0.0.1
#
# In federation.toml (peer HTTPS signed by this CA):
#   ca_cert_path = "/etc/sds/certs/federation-ca.pem"
#
# Client cert/key (${SITE}-client.pem/.key) are for future outbound mTLS in sync;
# Traefik/nginx uses local-sync-server.pem/.key for HTTPS on /sync/.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FEDERATION_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
CERT_DIR="${CERT_DIR:-${FEDERATION_ROOT}/certs}"

CA_NAME="${CA_NAME:-federation-ca}"
CA_DAYS="${CA_DAYS:-3650}"
CERT_DAYS="${CERT_DAYS:-825}"
SITE_NAME="${SITE_NAME:-crc}"
SERVER_CN="${SERVER_CN:-localhost}"
SERVER_DNS=()
SERVER_IPS=()
FORCE=0

usage() {
  sed -n '2,12p' "$0" | tail -n +2
  cat <<EOF

Commands:
  all       Create CA, client cert for SITE_NAME, and local sync server cert
  ca        Federation CA only (${CA_NAME}.pem / .key)
  client    Client cert for sync outbound mTLS (\${SITE}-client.pem)
  server    TLS cert for HTTPS terminator in front of sync (local-sync-server.pem)

Options:
  --cert-dir DIR     Output directory (default: federation/certs)
  --site-name NAME   Client cert basename (default: crc)
  --server-cn CN     Server certificate CN (default: localhost)
  --dns NAME         SAN DNS entry (repeatable; default: localhost if none given)
  --ip ADDR          SAN IP entry (repeatable; default: 127.0.0.1 if none given)
  --force            Overwrite existing files
  -h, --help         Show this help
EOF
}

log() {
  printf '==> %s\n' "$*"
}

need_openssl() {
  command -v openssl >/dev/null 2>&1 || {
    echo "openssl not found in PATH" >&2
    exit 1
  }
}

ensure_cert_dir() {
  mkdir -p "${CERT_DIR}"
}

write_if_missing() {
  local path=$1
  if [[ -f "${path}" && "${FORCE}" -ne 1 ]]; then
    echo "Refusing to overwrite ${path} (use --force)" >&2
    exit 1
  fi
}

generate_ca() {
  local ca_pem="${CERT_DIR}/${CA_NAME}.pem"
  local ca_key="${CERT_DIR}/${CA_NAME}.key"

  write_if_missing "${ca_pem}"
  write_if_missing "${ca_key}"

  log "CA -> ${ca_pem}"
  openssl genrsa -out "${ca_key}" 4096
  chmod 600 "${ca_key}"
  openssl req -x509 -new -nodes -key "${ca_key}" -sha256 -days "${CA_DAYS}" \
    -out "${ca_pem}" \
    -subj "/CN=SDS Federation Dev CA/O=Local Dev"
}

generate_client() {
  local ca_pem="${CERT_DIR}/${CA_NAME}.pem"
  local ca_key="${CERT_DIR}/${CA_NAME}.key"
  local client_key="${CERT_DIR}/${SITE_NAME}-client.key"
  local client_csr="${CERT_DIR}/${SITE_NAME}-client.csr"
  local client_pem="${CERT_DIR}/${SITE_NAME}-client.pem"

  [[ -f "${ca_pem}" && -f "${ca_key}" ]] || {
    echo "Run 'ca' first (missing ${CA_NAME}.pem/.key)" >&2
    exit 1
  }

  write_if_missing "${client_pem}"
  write_if_missing "${client_key}"

  log "Client (${SITE_NAME}) -> ${client_pem}"
  openssl genrsa -out "${client_key}" 2048
  chmod 600 "${client_key}"
  openssl req -new -key "${client_key}" -out "${client_csr}" \
    -subj "/CN=${SITE_NAME}-sync/O=SDS Federation"
  openssl x509 -req -in "${client_csr}" -CA "${ca_pem}" -CAkey "${ca_key}" \
    -CAcreateserial -out "${client_pem}" -days "${CERT_DAYS}" -sha256
}

generate_server() {
  local ca_pem="${CERT_DIR}/${CA_NAME}.pem"
  local ca_key="${CERT_DIR}/${CA_NAME}.key"
  local server_key="${CERT_DIR}/local-sync-server.key"
  local server_csr="${CERT_DIR}/local-sync-server.csr"
  local server_pem="${CERT_DIR}/local-sync-server.pem"
  local cnf="${CERT_DIR}/server-openssl.cnf"

  [[ -f "${ca_pem}" && -f "${ca_key}" ]] || {
    echo "Run 'ca' first (missing ${CA_NAME}.pem/.key)" >&2
    exit 1
  }

  if [[ ${#SERVER_DNS[@]} -eq 0 ]]; then
    SERVER_DNS=(localhost)
  fi
  if [[ ${#SERVER_IPS[@]} -eq 0 ]]; then
    SERVER_IPS=(127.0.0.1)
  fi

  write_if_missing "${server_pem}"
  write_if_missing "${server_key}"

  {
    echo "[req]"
    echo "distinguished_name = req_distinguished_name"
    echo "req_extensions = v3_req"
    echo "prompt = no"
    echo "[req_distinguished_name]"
    echo "CN = ${SERVER_CN}"
    echo "[v3_req]"
    echo "subjectAltName = @alt_names"
    echo "[alt_names]"
    local i=1
    for dns in "${SERVER_DNS[@]}"; do
      echo "DNS.${i} = ${dns}"
      i=$((i + 1))
    done
    i=1
    for ip in "${SERVER_IPS[@]}"; do
      echo "IP.${i} = ${ip}"
      i=$((i + 1))
    done
  } >"${cnf}"

  log "Server TLS -> ${server_pem} (CN=${SERVER_CN})"
  openssl genrsa -out "${server_key}" 2048
  chmod 600 "${server_key}"
  openssl req -new -key "${server_key}" -out "${server_csr}" -config "${cnf}"
  openssl x509 -req -in "${server_csr}" -CA "${ca_pem}" -CAkey "${ca_key}" \
    -CAcreateserial -out "${server_pem}" -days "${CERT_DAYS}" -sha256 \
    -extensions v3_req -extfile "${cnf}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h | --help)
      usage
      exit 0
      ;;
    --cert-dir)
      CERT_DIR=$2
      shift 2
      ;;
    --site-name)
      SITE_NAME=$2
      shift 2
      ;;
    --server-cn)
      SERVER_CN=$2
      shift 2
      ;;
    --dns)
      SERVER_DNS+=("$2")
      shift 2
      ;;
    --ip)
      SERVER_IPS+=("$2")
      shift 2
      ;;
    --force)
      FORCE=1
      shift
      ;;
    ca | client | server | all)
      COMMAND=$1
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

COMMAND="${COMMAND:-all}"

need_openssl
ensure_cert_dir

case "${COMMAND}" in
  ca)
    generate_ca
    ;;
  client)
    generate_client
    ;;
  server)
    generate_server
    ;;
  all)
    generate_ca
    generate_client
    generate_server
    log "Done. Trust bundle for peers: ${CERT_DIR}/${CA_NAME}.pem"
    ;;
  *)
    usage >&2
    exit 1
    ;;
esac
