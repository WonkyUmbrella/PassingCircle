#!/bin/bash
set -e

# Update CA certificates to trust our self-signed cert
update-ca-certificates

# Start Synapse
exec /start.py "$@"
