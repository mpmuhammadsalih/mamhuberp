-- =============================================================================
-- MamaHub dynamic media (hero, promos, category tiles, brand logos, banners)
-- =============================================================================

CREATE TABLE MH_MEDIA (
    MEDIA_ID                NUMBER          NOT NULL,
    PLACEMENT               VARCHAR2(50)    NOT NULL,
    REF_KEY                 VARCHAR2(120),
    TITLE                   VARCHAR2(200),
    SUBTITLE                VARCHAR2(2000 CHAR),
    IMAGE_URL               VARCHAR2(500)   NOT NULL,
    LINK_URL                VARCHAR2(500),
    ALT_TEXT                VARCHAR2(500 CHAR),
    SORT_ORDER              NUMBER          DEFAULT 0 NOT NULL,
    META_JSON               VARCHAR2(4000 CHAR),
    IS_ACTIVE               NUMBER(1)       DEFAULT 1 NOT NULL,
    CREATED_AT              TIMESTAMP       DEFAULT SYSTIMESTAMP NOT NULL,
    MODIFIED_AT             TIMESTAMP,
    CONSTRAINT PK_MH_MEDIA PRIMARY KEY (MEDIA_ID),
    CONSTRAINT CK_MH_MEDIA_ACTIVE CHECK (IS_ACTIVE IN (0, 1))
);

-- One row per ref_key for logo/specs/category tiles; product gallery allows many rows per item code.
CREATE UNIQUE INDEX UQ_MH_MEDIA_SINGLE_SLOT ON MH_MEDIA (
    CASE
        WHEN PLACEMENT IN (
            'storefront_logo', 'product_detail', 'showcase_banner', 'hero_bg',
            'age_group', 'category', 'brand', 'explore_category'
        )
        THEN PLACEMENT || CHR(1) || NVL(REF_KEY, ' ')
        ELSE NULL
    END
);

CREATE SEQUENCE SEQ_MH_MEDIA_ID START WITH 1 INCREMENT BY 1 NOCACHE NOCYCLE;
