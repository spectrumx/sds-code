#!/bin/sh
# Reference: https://opensearch.org/docs/latest/security/configuration/generate-certificates/

# Go to certs directory
cd opensearch/data/certs

# Root CA
openssl genrsa -out root-ca-key.pem 2048
openssl req -new -x509 -sha256 -key root-ca-key.pem -subj "/C=US/ST=INDIANA/L=SOUTH BEND/O=UNIVERSITY OF NOTRE DAME/OU=CRC/CN=sds.crc.nd.edu" -out root-ca.pem -days 730

# Admin cert
openssl genrsa -out admin-key-temp.pem 2048
openssl pkcs8 -inform PEM -outform PEM -in admin-key-temp.pem -topk8 -nocrypt -v1 PBE-SHA1-3DES -out admin-key.pem
openssl req -new -key admin-key.pem -subj "/C=US/ST=INDIANA/L=SOUTH BEND/O=UNIVERSITY OF NOTRE DAME/OU=CRC/CN=admin" -out admin.csr
openssl x509 -req -in admin.csr -CA root-ca.pem -CAkey root-ca-key.pem -CAcreateserial -sha256 -out admin.pem -days 730

# Opensearch cert
openssl genrsa -out opensearch-key-temp.pem 2048
openssl pkcs8 -inform PEM -outform PEM -in opensearch-key-temp.pem -topk8 -nocrypt -v1 PBE-SHA1-3DES -out opensearch-key.pem
openssl req -new -key opensearch-key.pem -subj "/C=US/ST=INDIANA/L=SOUTH BEND/O=UNIVERSITY OF NOTRE DAME/OU=CRC/CN=sds.crc.nd.edu" -out opensearch.csr
echo 'subjectAltName=DNS:sds.crc.nd.edu' > opensearch.ext
openssl x509 -req -in opensearch.csr -CA root-ca.pem -CAkey root-ca-key.pem -CAcreateserial -sha256 -out opensearch.pem -days 730 -extfile opensearch.ext

# Django cert
openssl genrsa -out django-key-temp.pem 2048
openssl pkcs8 -inform PEM -outform PEM -in django-key-temp.pem -topk8 -nocrypt -v1 PBE-SHA1-3DES -out django-key.pem
openssl req -new -key django-key.pem -subj "/C=US/ST=INDIANA/L=SOUTH BEND/O=UNIVERSITY OF NOTRE DAME/OU=CRC/CN=sds.crc.nd.edu" -out django.csr
echo 'subjectAltName=DNS:sds.crc.nd.edu' > django.ext
openssl x509 -req -in django.csr -CA root-ca.pem -CAkey root-ca-key.pem -CAcreateserial -sha256 -out django.pem -days 730 -extfile django.ext

# Cleanup
rm admin-key-temp.pem
rm admin.csr
rm opensearch-key-temp.pem
rm opensearch.csr
rm opensearch.ext
rm django-key-temp.pem
rm django.csr
rm django.ext
