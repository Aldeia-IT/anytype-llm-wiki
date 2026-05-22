"""Canonical wiki type schema — the single source of truth.

Defines the six wiki object types, their property definitions (key + Anytype
format), the default domain tags, and the schema version. The bootstrap command
(next worker) reads these to idempotently create types, properties, and tags in
an Anytype space.

Every type_key and every default domain tag is namespaced with the ``wiki_``
prefix to avoid collisions with a user's pre-existing types/tags.
"""

# Semver x.y.z. v0.2.0 ships the foundation tranche; MUST be > "0.1.0".
WIKI_SCHEMA_VERSION = "0.2.0"

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

# The six canonical wiki object types. Each entry:
#   type_key:   stable wiki_-prefixed key used in API calls
#   name:       human-readable label shown in the Anytype UI
#   properties: list of {property_key, format} dicts (Anytype property formats:
#               text, url, date, number, select, multi_select, objects)
WIKI_TYPES = [
    {
        "type_key": "wiki_source",
        "name": "Source",
        "properties": [
            {"property_key": "wiki_url", "format": "url"},
            {"property_key": "wiki_file_path", "format": "text"},
            {"property_key": "wiki_excerpt", "format": "text"},
            {"property_key": "wiki_ingested_at", "format": "date"},
            {"property_key": "wiki_domain_tags", "format": "multi_select"},
            {"property_key": "wiki_source_type", "format": "select"},
        ],
    },
    {
        "type_key": "wiki_entity",
        "name": "Entity",
        "properties": [
            {"property_key": "wiki_description", "format": "text"},
            {"property_key": "wiki_facts", "format": "text"},
            {"property_key": "wiki_relations", "format": "objects"},
            {"property_key": "wiki_sources", "format": "objects"},
            {"property_key": "wiki_domain_tags", "format": "multi_select"},
            {"property_key": "wiki_contradictions", "format": "objects"},
            {"property_key": "wiki_status", "format": "select"},
            {"property_key": "wiki_last_reviewed", "format": "date"},
        ],
    },
    {
        "type_key": "wiki_concept",
        "name": "Concept",
        "properties": [
            {"property_key": "wiki_definition", "format": "text"},
            {"property_key": "wiki_open_questions", "format": "text"},
            {"property_key": "wiki_related", "format": "objects"},
            {"property_key": "wiki_sources", "format": "objects"},
            {"property_key": "wiki_domain_tags", "format": "multi_select"},
            {"property_key": "wiki_contradictions", "format": "objects"},
            {"property_key": "wiki_status", "format": "select"},
        ],
    },
    {
        "type_key": "wiki_comparison",
        "name": "Comparison",
        "properties": [
            {"property_key": "wiki_subjects", "format": "objects"},
            {"property_key": "wiki_dimensions", "format": "text"},
            {"property_key": "wiki_verdict", "format": "text"},
            {"property_key": "wiki_sources", "format": "objects"},
        ],
    },
    {
        "type_key": "wiki_query",
        "name": "Query",
        "properties": [
            {"property_key": "wiki_question", "format": "text"},
            {"property_key": "wiki_answer", "format": "text"},
            {"property_key": "wiki_drew_from", "format": "objects"},
            {"property_key": "wiki_asked_at", "format": "date"},
        ],
    },
    {
        "type_key": "wiki_log",
        "name": "WikiLog",
        "properties": [
            {"property_key": "wiki_action", "format": "select"},
            {"property_key": "wiki_subject", "format": "text"},
            {"property_key": "wiki_objects_created", "format": "number"},
            {"property_key": "wiki_objects_updated", "format": "number"},
            {"property_key": "wiki_timestamp", "format": "date"},
            {"property_key": "wiki_notes", "format": "text"},
        ],
    },
]
