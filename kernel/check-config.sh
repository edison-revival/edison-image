#!/bin/sh
# Usage: check-config.sh .config required.txt
# Fails if any CONFIG_X=value line in required.txt isn't exactly present in .config.
config="$1"
required="$2"
status=0
while IFS= read -r line; do
    case "$line" in ''|'#'*) continue ;; esac
    if ! grep -qx "$line" "$config"; then
        sym="${line%%=*}"
        actual="$(grep -E "^(# )?${sym}[= ]" "$config" || echo "${sym} missing")"
        echo "config check failed: want ${line}, got: ${actual}" >&2
        status=1
    fi
done < "$required"
[ "$status" -eq 0 ] && echo "config check passed ($(grep -cv -e '^#' -e '^$' "$required") symbols)"
exit "$status"
