"""Canonical wiki type schema — the single source of truth.

Defines the six wiki object types, their property definitions (key + display
name + Anytype format), the default domain tags, and the schema version. The
bootstrap command reads these to idempotently create types, properties, and
tags in an Anytype space.

Every type_key and every default domain tag is namespaced with the ``wiki_``
prefix to avoid collisions with a user's pre-existing types/tags.

API-contract notes (verified against the Anytype local API, version
2025-11-08):
- ``POST /v1/spaces/{id}/types`` REQUIRES ``name``, ``plural_name`` and
  ``layout``; the layout enum is {basic, profile, action, note} (NOT
  "collection"). Inline ``properties`` entries REQUIRE ``key``, ``name`` and
  ``format`` and are created-and-linked in one call (linking a pre-existing
  property key across multiple types is accepted).
- ``POST /v1/spaces/{id}/properties`` REQUIRES ``name`` + ``format``.
- Select/multi-select option values are *tags*, created via
  ``POST /v1/spaces/{id}/properties/{property_id}/tags`` with a REQUIRED
  ``color`` drawn from ``TAG_COLOR_PALETTE``.
"""

# Semver x.y.z. v0.3.0 ships the wiki_ingest compile pipeline; MUST be > "0.1.0".
WIKI_SCHEMA_VERSION = "0.3.0"

# Allowed tag colors per the Anytype API (CreateTagRequest.color enum). Tags are
# assigned a color by cycling this palette deterministically at bootstrap time.
TAG_COLOR_PALETTE = [
    "grey",
    "yellow",
    "orange",
    "red",
    "pink",
    "purple",
    "blue",
    "ice",
    "teal",
    "lime",
]

# The seven default domain tags applied to the wiki_domain_tags multi-select.
DEFAULT_DOMAIN_TAGS = [
    "wiki_ai-research",
    "wiki_infrastructure",
    "wiki_business",
    "wiki_engineering",
    "wiki_governance",
    "wiki_science",
    "wiki_other",
]

# The property key whose multi-select options carry the domain taxonomy.
DOMAIN_TAGS_PROPERTY_KEY = "wiki_domain_tags"

# The property key used to stamp the running schema version onto bootstrap's
# WikiLog marker object (read back for upgrade detection).
SCHEMA_VERSION_PROPERTY_KEY = "wiki_schema_version"

# The six canonical wiki object types. Each entry:
#   type_key:    stable wiki_-prefixed key used in API calls
#   name:        singular human-readable label shown in the Anytype UI
#   plural_name: plural label (REQUIRED by the create-type API)
#   layout:      Anytype type layout (REQUIRED); all wiki types use "basic"
#   properties:  list of {property_key, name, format} dicts (Anytype formats:
#                text, url, date, number, select, multi_select, objects)
WIKI_TYPES = [
    {
        "type_key": "wiki_source",
        "name": "Source",
        "plural_name": "Sources",
        "layout": "basic",
        "properties": [
            {"property_key": "wiki_url", "name": "URL", "format": "url"},
            {"property_key": "wiki_file_path", "name": "File Path", "format": "text"},
            {"property_key": "wiki_excerpt", "name": "Excerpt", "format": "text"},
            {"property_key": "wiki_ingested_at", "name": "Ingested At", "format": "date"},
            {"property_key": "wiki_domain_tags", "name": "Domain Tags", "format": "multi_select"},
            {"property_key": "wiki_source_type", "name": "Source Type", "format": "select"},
        ],
    },
    {
        "type_key": "wiki_entity",
        "name": "Entity",
        "plural_name": "Entities",
        "layout": "basic",
        "properties": [
            {"property_key": "wiki_description", "name": "Description", "format": "text"},
            {"property_key": "wiki_facts", "name": "Facts", "format": "text"},
            {"property_key": "wiki_relations", "name": "Relations", "format": "objects"},
            {"property_key": "wiki_sources", "name": "Sources", "format": "objects"},
            {"property_key": "wiki_domain_tags", "name": "Domain Tags", "format": "multi_select"},
            {"property_key": "wiki_contradictions", "name": "Contradictions", "format": "objects"},
            {"property_key": "wiki_status", "name": "Status", "format": "select"},
            {"property_key": "wiki_last_reviewed", "name": "Last Reviewed", "format": "date"},
        ],
    },
    {
        "type_key": "wiki_concept",
        "name": "Concept",
        "plural_name": "Concepts",
        "layout": "basic",
        "properties": [
            {"property_key": "wiki_definition", "name": "Definition", "format": "text"},
            {"property_key": "wiki_open_questions", "name": "Open Questions", "format": "text"},
            {"property_key": "wiki_related", "name": "Related", "format": "objects"},
            {"property_key": "wiki_sources", "name": "Sources", "format": "objects"},
            {"property_key": "wiki_domain_tags", "name": "Domain Tags", "format": "multi_select"},
            {"property_key": "wiki_contradictions", "name": "Contradictions", "format": "objects"},
            {"property_key": "wiki_status", "name": "Status", "format": "select"},
        ],
    },
    {
        "type_key": "wiki_comparison",
        "name": "Comparison",
        "plural_name": "Comparisons",
        "layout": "basic",
        "properties": [
            {"property_key": "wiki_subjects", "name": "Subjects", "format": "objects"},
            {"property_key": "wiki_dimensions", "name": "Dimensions", "format": "text"},
            {"property_key": "wiki_verdict", "name": "Verdict", "format": "text"},
            {"property_key": "wiki_sources", "name": "Sources", "format": "objects"},
        ],
    },
    {
        "type_key": "wiki_query",
        "name": "Query",
        "plural_name": "Queries",
        "layout": "basic",
        "properties": [
            {"property_key": "wiki_question", "name": "Question", "format": "text"},
            {"property_key": "wiki_answer", "name": "Answer", "format": "text"},
            {"property_key": "wiki_drew_from", "name": "Drew From", "format": "objects"},
            {"property_key": "wiki_asked_at", "name": "Asked At", "format": "date"},
        ],
    },
    {
        "type_key": "wiki_log",
        "name": "WikiLog",
        "plural_name": "WikiLogs",
        "layout": "basic",
        "properties": [
            {"property_key": "wiki_action", "name": "Action", "format": "select"},
            {"property_key": "wiki_subject", "name": "Subject", "format": "text"},
            {"property_key": "wiki_objects_created", "name": "Objects Created", "format": "number"},
            {"property_key": "wiki_objects_updated", "name": "Objects Updated", "format": "number"},
            {"property_key": "wiki_timestamp", "name": "Timestamp", "format": "date"},
            {"property_key": "wiki_notes", "name": "Notes", "format": "text"},
            {"property_key": "wiki_schema_version", "name": "Schema Version", "format": "text"},
        ],
    },
]
