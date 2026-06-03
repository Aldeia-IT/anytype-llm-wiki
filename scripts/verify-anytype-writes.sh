#!/usr/bin/env bash
#
# verify-anytype-writes.sh — maintainer-local verification of Anytype write
# semantics (spec §Verification Script, AC #7).
#
# Runs three live-API probes (PATCH body, PATCH property, FilterExpression
# search counts) against a THROWAWAY probe object that this script creates and
# deletes itself. No operator-owned object is ever touched.
#
# This script is NOT run in CI — it requires a live Anytype desktop app. It is
# named in the v0.2.0 pre-release checklist as a local-only step.
#
# Environment variables consumed:
#   ANYTYPE_API_KEY      (required) bearer token with write scope
#   ANYTYPE_SPACE_ID     (required) space in which the probe artifacts are made
#   ANYTYPE_API_URL      (optional) default http://127.0.0.1:31012
#   ANYTYPE_API_VERSION  (optional) default 2025-11-08
#
# NOTE: ANYTYPE_OBJECT_ID is deliberately NOT consumed — earlier drafts expected
# an operator-supplied object id, which was a data-loss foot-gun. The script
# creates and deletes its own probe object internally.
#
# Requires: bash, curl, jq.

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
ANYTYPE_API_URL="${ANYTYPE_API_URL:-http://127.0.0.1:31012}"
ANYTYPE_API_VERSION="${ANYTYPE_API_VERSION:-2025-11-08}"
ANYTYPE_API_KEY="${ANYTYPE_API_KEY:-}"
ANYTYPE_SPACE_ID="${ANYTYPE_SPACE_ID:-}"

PATCH_DECISION_PATH=".aldeia/140-wiki-library-module-port-llm-wiki-pattern-onto-any/patch-decision.md"

# Probe artifact identifiers — initialized empty so the cleanup trap is a safe
# no-op if the script is interrupted before the artifacts are created.
PROBE_TYPE_KEY="__wiki_verify_probe__"
PROBE_TYPE_ID=""
PROBE_OBJECT_ID=""
PROBE_TYPE_CREATED_BY_US=""

# ---------------------------------------------------------------------------
# Preamble banner (printed BEFORE any probe is created)
# ---------------------------------------------------------------------------
cat >&2 <<'BANNER'
============================================================================
  verify-anytype-writes.sh
  This script CREATES and DELETES temporary probe artifacts in the target
  Anytype space (a probe type "__wiki_verify_probe__" and a probe object
  "__verify-anytype-writes-probe-<timestamp>__"). It does NOT touch any of
  your existing objects. The artifacts are removed on exit.
============================================================================
BANNER

if [[ -z "$ANYTYPE_API_KEY" ]]; then
  echo "ERROR: ANYTYPE_API_KEY is required." >&2
  exit 2
fi
if [[ -z "$ANYTYPE_SPACE_ID" ]]; then
  echo "ERROR: ANYTYPE_SPACE_ID is required." >&2
  exit 2
fi

auth_header="Authorization: Bearer $ANYTYPE_API_KEY"
version_header="Anytype-Version: $ANYTYPE_API_VERSION"
content_header="Content-Type: application/json"

# ---------------------------------------------------------------------------
# Cleanup function + trap — installed BEFORE the probe is created so a SIGINT
# arriving during probe creation still triggers a (guarded, no-op-safe) cleanup.
# ---------------------------------------------------------------------------
cleanup() {
  local rc=$?
  if [[ -n "${PROBE_OBJECT_ID:-}" ]]; then
    local delete_response
    delete_response=$(curl -sS -w "\n%{http_code}" -X DELETE \
      "$ANYTYPE_API_URL/v1/spaces/$ANYTYPE_SPACE_ID/objects/$PROBE_OBJECT_ID" \
      -H "$auth_header" \
      -H "$version_header" 2>&1 || true)
    local http_code="${delete_response##*$'\n'}"
    local body="${delete_response%$'\n'*}"
    if [[ "$http_code" != 2* ]]; then
      echo "WARN: probe object DELETE returned HTTP $http_code — zombie probe $PROBE_OBJECT_ID may remain. Response: $body" >&2
    fi
  fi
  if [[ -n "${PROBE_TYPE_CREATED_BY_US:-}" && "${PROBE_TYPE_CREATED_BY_US:-}" == "1" ]]; then
    # Delete by type id when known (the API keys deletion by id, not key);
    # fall back to the key for older API behavior.
    local type_ref="${PROBE_TYPE_ID:-$PROBE_TYPE_KEY}"
    local type_response
    type_response=$(curl -sS -w "\n%{http_code}" -X DELETE \
      "$ANYTYPE_API_URL/v1/spaces/$ANYTYPE_SPACE_ID/types/$type_ref" \
      -H "$auth_header" \
      -H "$version_header" 2>&1 || true)
    local type_http_code="${type_response##*$'\n'}"
    local type_body="${type_response%$'\n'*}"
    if [[ "$type_http_code" != 2* ]]; then
      echo "WARN: probe type DELETE returned HTTP $type_http_code — zombie type $PROBE_TYPE_KEY may remain. Response: $type_body" >&2
    fi
  fi
  return $rc
}
trap cleanup EXIT INT TERM

# ---------------------------------------------------------------------------
# Setup (after trap is installed): create the probe type, then the probe object.
# ---------------------------------------------------------------------------
echo "Creating probe type '$PROBE_TYPE_KEY' ..." >&2
type_create_response=$(curl -sS -w "\n%{http_code}" -X POST "$ANYTYPE_API_URL/v1/spaces/$ANYTYPE_SPACE_ID/types" \
  -H "$auth_header" -H "$version_header" -H "$content_header" \
  -d "{\"key\":\"$PROBE_TYPE_KEY\",\"name\":\"Wiki Verify Probe\",\"plural_name\":\"Wiki Verify Probes\",\"layout\":\"basic\"}" 2>&1 || true)
type_create_code="${type_create_response##*$'\n'}"
type_create_body="${type_create_response%$'\n'*}"
if [[ "$type_create_code" == 2* ]]; then
  PROBE_TYPE_CREATED_BY_US=1
  # The API normalizes the key (snake_case) and returns the canonical key + id;
  # use them for the object create, filter search, and cleanup.
  PROBE_TYPE_ID="$(echo "$type_create_body" | jq -r '.type.id // empty')"
  canonical_key="$(echo "$type_create_body" | jq -r '.type.key // empty')"
  if [[ -n "$canonical_key" ]]; then PROBE_TYPE_KEY="$canonical_key"; fi
  echo "Probe type created (key=$PROBE_TYPE_KEY id=$PROBE_TYPE_ID)." >&2
else
  # The type may already exist from a previous run; proceed without claiming
  # ownership so cleanup does not delete a type we did not create.
  echo "NOTE: probe type create returned HTTP $type_create_code (may already exist); not claiming ownership." >&2
fi

probe_timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
probe_name="__verify-anytype-writes-probe-${probe_timestamp}__"
echo "Creating probe object '$probe_name' ..." >&2
object_create_response=$(curl -sS -w "\n%{http_code}" -X POST \
  "$ANYTYPE_API_URL/v1/spaces/$ANYTYPE_SPACE_ID/objects" \
  -H "$auth_header" -H "$version_header" -H "$content_header" \
  -d "{\"type_key\":\"$PROBE_TYPE_KEY\",\"name\":\"$probe_name\"}" 2>&1 || true)
object_create_code="${object_create_response##*$'\n'}"
object_create_body="${object_create_response%$'\n'*}"
if [[ "$object_create_code" != 2* ]]; then
  echo "ERROR: probe object create failed (HTTP $object_create_code). Response: $object_create_body" >&2
  exit 1
fi
PROBE_OBJECT_ID="$(echo "$object_create_body" | jq -r '.object.id // .id // empty')"
if [[ -z "$PROBE_OBJECT_ID" ]]; then
  echo "ERROR: could not parse probe object id from create response." >&2
  exit 1
fi
echo "Probe object id: $PROBE_OBJECT_ID" >&2

# ---------------------------------------------------------------------------
# Probe 1 — PATCH body update
# ---------------------------------------------------------------------------
body_marker="verify-body-${probe_timestamp}"
patch_body_decision="error"
patch_body_response=$(curl -sS -w "\n%{http_code}" -X PATCH \
  "$ANYTYPE_API_URL/v1/spaces/$ANYTYPE_SPACE_ID/objects/$PROBE_OBJECT_ID" \
  -H "$auth_header" -H "$version_header" -H "$content_header" \
  -d "{\"body\":\"$body_marker\"}" 2>&1 || true)
patch_body_code="${patch_body_response##*$'\n'}"
if [[ "$patch_body_code" == 2* ]]; then
  reread=$(curl -sS "$ANYTYPE_API_URL/v1/spaces/$ANYTYPE_SPACE_ID/objects/$PROBE_OBJECT_ID?format=md" \
    -H "$auth_header" -H "$version_header" 2>&1 || true)
  if echo "$reread" | grep -q "$body_marker"; then
    patch_body_decision="works"
  else
    patch_body_decision="silently_ignored"
  fi
else
  patch_body_decision="error"
fi
echo "Probe 1 (PATCH body): $patch_body_decision" >&2

# ---------------------------------------------------------------------------
# Probe 2 — PATCH property (name) update
# ---------------------------------------------------------------------------
new_name="${probe_name}-renamed"
patch_prop_decision="error"
patch_prop_response=$(curl -sS -w "\n%{http_code}" -X PATCH \
  "$ANYTYPE_API_URL/v1/spaces/$ANYTYPE_SPACE_ID/objects/$PROBE_OBJECT_ID" \
  -H "$auth_header" -H "$version_header" -H "$content_header" \
  -d "{\"name\":\"$new_name\"}" 2>&1 || true)
patch_prop_code="${patch_prop_response##*$'\n'}"
if [[ "$patch_prop_code" == 2* ]]; then
  reread=$(curl -sS "$ANYTYPE_API_URL/v1/spaces/$ANYTYPE_SPACE_ID/objects/$PROBE_OBJECT_ID?format=md" \
    -H "$auth_header" -H "$version_header" 2>&1 || true)
  if echo "$reread" | jq -e --arg n "$new_name" '.object.name == $n' >/dev/null 2>&1; then
    patch_prop_decision="works"
  else
    patch_prop_decision="silently_ignored"
  fi
else
  patch_prop_decision="error"
fi
echo "Probe 2 (PATCH property): $patch_prop_decision" >&2

# ---------------------------------------------------------------------------
# Probe 3 — FilterExpression search counts
# ---------------------------------------------------------------------------
filter_decision="partial"
search_unfiltered=$(curl -sS -X POST "$ANYTYPE_API_URL/v1/spaces/$ANYTYPE_SPACE_ID/search" \
  -H "$auth_header" -H "$version_header" -H "$content_header" \
  -d '{"query":""}' 2>&1 || true)
count_unfiltered=$(echo "$search_unfiltered" | jq -r '.data | length // 0' 2>/dev/null || echo 0)

search_typed=$(curl -sS -X POST "$ANYTYPE_API_URL/v1/spaces/$ANYTYPE_SPACE_ID/search" \
  -H "$auth_header" -H "$version_header" -H "$content_header" \
  -d "{\"query\":\"\",\"filter\":{\"condition\":\"and\",\"filters\":[{\"key\":\"type_key\",\"condition\":\"eq\",\"value\":\"$PROBE_TYPE_KEY\"}]}}" 2>&1 || true)
count_typed=$(echo "$search_typed" | jq -r '.data | length // 0' 2>/dev/null || echo 0)

search_impossible=$(curl -sS -X POST "$ANYTYPE_API_URL/v1/spaces/$ANYTYPE_SPACE_ID/search" \
  -H "$auth_header" -H "$version_header" -H "$content_header" \
  -d '{"query":"","filter":{"condition":"and","filters":[{"key":"type_key","condition":"eq","value":"__no_such_type_key__"}]}}' 2>&1 || true)
count_impossible=$(echo "$search_impossible" | jq -r '.data | length // 0' 2>/dev/null || echo 0)

if [[ "$count_impossible" == "0" && "$count_typed" -ge 1 && "$count_unfiltered" -ge "$count_typed" ]]; then
  filter_decision="works"
elif [[ "$count_typed" == "$count_unfiltered" && "$count_impossible" == "$count_unfiltered" ]]; then
  filter_decision="no_op"
else
  filter_decision="partial"
fi
echo "Probe 3 (FilterExpression): $filter_decision (unfiltered=$count_unfiltered typed=$count_typed impossible=$count_impossible)" >&2

# ---------------------------------------------------------------------------
# Decision block — emitted to stdout AND appended to patch-decision.md
# ---------------------------------------------------------------------------
if [[ "$patch_body_decision" == "works" ]]; then
  implementation_path="primary_patch"
else
  implementation_path="fallback_properties_only"
fi

decision_ts="$(date -u +%Y-%m-%dT%H:%MZ)"
decision_block=$(cat <<EOF
ANYTYPE_VERIFICATION_DECISION
  anytype_version:         $ANYTYPE_API_VERSION
  timestamp:               $decision_ts
  patch_body_updates:      $patch_body_decision
  patch_property_updates:  $patch_prop_decision
  filter_expression:       $filter_decision
  implementation_path:     $implementation_path
END
EOF
)

echo "$decision_block"

if [[ -d "$(dirname "$PATCH_DECISION_PATH")" ]]; then
  {
    echo ""
    echo "$decision_block"
  } >> "$PATCH_DECISION_PATH"
  echo "Decision appended to $PATCH_DECISION_PATH" >&2
else
  echo "NOTE: $(dirname "$PATCH_DECISION_PATH") not present; decision printed to stdout only." >&2
fi
