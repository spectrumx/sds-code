#!/bin/bash
# Reference: https://opensearch.org/docs/latest/security/configuration/generate-certificates/

set -euo pipefail
RUN_TIMESTAMP=$(date +%s)

DIR_HOST_CERTS="opensearch/data/certs"                      # where new certs will be placed
DIR_HOST_CERTS_TEMP="opensearch/data/.certs-$RUN_TIMESTAMP" # where new certs are generated; no trailing slash
DIR_BACKUP="$DIR_HOST_CERTS_TEMP-backup"                    # backup location for existing certs
DIR_RETURN="$(pwd)"                                         # return to this directory after script execution
OPEN_SEARCH_CONTAINER_NAME="sds-gateway-prod-opensearch"
ROOT_CA_PEM="root-ca.pem"
ROOT_CA_KEY_PEM="root-ca-key.pem"

# creates temp directory; checks if script can run
function pre_conditions() {
    mkdir -p "$DIR_HOST_CERTS_TEMP"
    if ! command -v openssl &>/dev/null; then
        echo -e "\e[31m\topenssl is required\e[0m"
        return 1
    fi
    if ! command -v rsync &>/dev/null; then
        echo -e "\e[31m\trsync is required\e[0m"
        return 1
    fi
}

# generate cert files in current directory
function generate_certs() {

    # Root CA
    openssl genrsa -out $ROOT_CA_KEY_PEM 2048
    openssl req -new -x509 -sha256 -key $ROOT_CA_KEY_PEM -subj "/C=US/ST=INDIANA/L=SOUTH BEND/O=UNIVERSITY OF NOTRE DAME/OU=CRC/CN=$OPEN_SEARCH_CONTAINER_NAME" -out $ROOT_CA_PEM -days 730

    # Admin cert
    openssl genrsa -out admin-key-temp.pem 2048
    openssl pkcs8 -inform PEM -outform PEM -in admin-key-temp.pem -topk8 -nocrypt -v1 PBE-SHA1-3DES -out admin-key.pem
    openssl req -new -key admin-key.pem -subj "/C=US/ST=INDIANA/L=SOUTH BEND/O=UNIVERSITY OF NOTRE DAME/OU=CRC/CN=admin" -out admin.csr

    openssl x509 -req -in admin.csr -CA $ROOT_CA_PEM -CAkey $ROOT_CA_KEY_PEM -CAcreateserial -sha256 -out admin.pem -days 730
    openssl x509 -req -in admin.csr -CA $ROOT_CA_PEM -CAkey $ROOT_CA_KEY_PEM -CAcreateserial -sha256 -out admin.pem -days 730

    # Opensearch cert
    openssl genrsa -out opensearch-key-temp.pem 2048
    openssl pkcs8 -inform PEM -outform PEM -in opensearch-key-temp.pem -topk8 -nocrypt -v1 PBE-SHA1-3DES -out opensearch-key.pem
    openssl req -new -key opensearch-key.pem -subj "/C=US/ST=INDIANA/L=SOUTH BEND/O=UNIVERSITY OF NOTRE DAME/OU=CRC/CN=$OPEN_SEARCH_CONTAINER_NAME" -out opensearch.csr
    echo "subjectAltName=DNS:$OPEN_SEARCH_CONTAINER_NAME" >opensearch.ext
    openssl x509 -req -in opensearch.csr -CA $ROOT_CA_PEM -CAkey $ROOT_CA_KEY_PEM -CAcreateserial -sha256 -out opensearch.pem -days 730 -extfile opensearch.ext

    # Django cert
    openssl genrsa -out django-key-temp.pem 2048
    openssl pkcs8 -inform PEM -outform PEM -in django-key-temp.pem -topk8 -nocrypt -v1 PBE-SHA1-3DES -out django-key.pem
    openssl req -new -key django-key.pem -subj "/C=US/ST=INDIANA/L=SOUTH BEND/O=UNIVERSITY OF NOTRE DAME/OU=CRC/CN=$OPEN_SEARCH_CONTAINER_NAME" -out django.csr
    echo "subjectAltName=DNS:$OPEN_SEARCH_CONTAINER_NAME" >django.ext
    openssl x509 -req -in django.csr -CA $ROOT_CA_PEM -CAkey $ROOT_CA_KEY_PEM -CAcreateserial -sha256 -out django.pem -days 730 -extfile django.ext

}

# replace existing certs with the generated ones
function replace_certs() {
    if [ ! -d "$DIR_HOST_CERTS_TEMP" ] || [ ! "$(ls -A "$DIR_HOST_CERTS_TEMP")" ]; then
        echo -e "\e[31mNo generated files found in '$DIR_HOST_CERTS_TEMP'. Something went wrong with the certs creation.\e[0m"
        return 1
    fi
    if [ ! "$(ls -A $DIR_HOST_CERTS)" ]; then
        echo "Copying certs to '$DIR_HOST_CERTS'"
        rsync -av "$DIR_HOST_CERTS_TEMP/" "$DIR_HOST_CERTS"
    else
        echo "Backing up existing certs to '$DIR_BACKUP'"
        mkdir -p "$DIR_BACKUP"
        rsync -a "$DIR_HOST_CERTS/" "$DIR_BACKUP"
        echo "Replacing certs in '$DIR_HOST_CERTS'"
        rsync -av "$DIR_HOST_CERTS_TEMP/" "$DIR_HOST_CERTS"
    fi
    rm -rf "$DIR_HOST_CERTS_TEMP"
    echo -e "\e[32mCerts stored in '$DIR_HOST_CERTS'\e[0m"
}

function cleanup_current_dir() {

    # Cleanup
    rm admin-key-temp.pem
    rm admin.csr
    rm opensearch-key-temp.pem
    rm opensearch.csr
    rm opensearch.ext
    rm django-key-temp.pem
    rm django.csr
    rm django.ext

}

function fix_permissions() {
    chmod 700 "$DIR_HOST_CERTS"
    chmod 600 "$DIR_HOST_CERTS"/*
}

function main() {
    pre_conditions || exit 1
    cd "$DIR_HOST_CERTS_TEMP" || exit 1
    generate_certs
    cleanup_current_dir
    cd "$DIR_RETURN" || exit 0
    replace_certs
    fix_permissions
}

main
