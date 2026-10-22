erDiagram
    demo_catalog_nodes ||--o{ demo_catalog_attributes : "has (ON DELETE CASCADE)"

    demo_catalog_nodes {
        INTEGER id PK "AUTOINCREMENT, NOT NULL"
         VARCHAR(64) code UK "NOT NULL, CHECK(length(trim(code)) > 0)"
        VARCHAR(128) label "NOT NULL, CHECK(length(trim(label)) > 0)"
        VARCHAR(16) status "NOT NULL, DEFAULT 'DRAFT', CHECK(IN 'DRAFT','ACTIVE','ARCHIVED')"
        INTEGER priority "NOT NULL, DEFAULT 0, CHECK(priority >= 0)"
        TEXT description "NULLABLE"
        DATETIME_UTC created_at "NOT NULL, Python UTC authoritative"
        DATETIME_UTC updated_at "NOT NULL, Python UTC authoritative"
        BOOLEAN is_deleted "NOT NULL, DEFAULT FALSE (Opt-in SoftDeleteMixin)"
        DATETIME_UTC deleted_at "NULLABLE, CHECK consistency with is_deleted"
    }

    demo_catalog_attributes {
        INTEGER id PK "AUTOINCREMENT, NOT NULL"
        INTEGER node_id FK "NOT NULL, REFERENCES demo_catalog_nodes(id) ON DELETE CASCADE"
        VARCHAR(64) attr_key "NOT NULL, CHECK(length(trim(attr_key)) > 0)"
        VARCHAR(256) attr_value "NOT NULL"
        FLOAT metric_value "NOT NULL, DEFAULT 0.0, CHECK(metric_value >= 0.0)"
        DATETIME_UTC created_at "NOT NULL, Python UTC authoritative"
        DATETIME_UTC updated_at "NOT NULL, Python UTC authoritative"
    }