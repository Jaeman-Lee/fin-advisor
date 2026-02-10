#!/bin/bash
# validate_readonly_query.sh
# Pre-execution hook to validate that SQL queries are read-only (SELECT only).
# Used by the db-agent to prevent accidental data modification.
#
# Usage: validate_readonly_query.sh "<sql_query>"
# Exit codes: 0 = safe (SELECT only), 1 = unsafe (mutation detected)

set -euo pipefail

QUERY="${1:-}"

if [ -z "$QUERY" ]; then
    echo "ERROR: No query provided"
    exit 1
fi

# Normalize: uppercase, trim whitespace
UPPER_QUERY=$(echo "$QUERY" | tr '[:lower:]' '[:upper:]' | sed 's/^[[:space:]]*//')

# Allow only SELECT statements
if [[ "$UPPER_QUERY" =~ ^SELECT ]]; then
    # Check for dangerous embedded statements
    DANGEROUS_KEYWORDS="INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|REPLACE|ATTACH|DETACH|PRAGMA"
    if echo "$UPPER_QUERY" | grep -qE "\b($DANGEROUS_KEYWORDS)\b"; then
        echo "BLOCKED: Query contains dangerous keyword"
        exit 1
    fi
    echo "OK: Read-only query validated"
    exit 0
else
    echo "BLOCKED: Only SELECT queries are allowed"
    exit 1
fi
