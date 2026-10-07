-- Default CMS pages for storefront footer links.

INSERT INTO MH_CMS_PAGE (
    CMS_PAGE_ID, PAGE_CODE, PAGE_TITLE, SLUG, PAGE_TYPE, CONTENT_HTML,
    META_DESCRIPTION, IS_PUBLISHED, SORT_ORDER, CREATED_AT
)
SELECT SEQ_MH_CMS_PAGE_ID.NEXTVAL, 'FAQ', 'Frequently Asked Questions', 'faq', 'STATIC',
       '<h2>Ordering</h2><p>Place orders online for home delivery or store pickup across Qatar.</p><h2>Returns</h2><p>Most toys can be returned within 14 days with receipt.</p>',
       'MamaHub FAQ', 1, 10, SYSTIMESTAMP FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM MH_CMS_PAGE WHERE PAGE_CODE = 'FAQ');

INSERT INTO MH_CMS_PAGE (
    CMS_PAGE_ID, PAGE_CODE, PAGE_TITLE, SLUG, PAGE_TYPE, CONTENT_HTML,
    META_DESCRIPTION, IS_PUBLISHED, SORT_ORDER, CREATED_AT
)
SELECT SEQ_MH_CMS_PAGE_ID.NEXTVAL, 'CONTACT', 'Contact Us', 'contact', 'STATIC',
       '<p>Email: hello@mamahub.store</p><p>Phone: +974 0000 0000</p><p>We love helping families find the perfect toy.</p>',
       'Contact MamaHub', 1, 20, SYSTIMESTAMP FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM MH_CMS_PAGE WHERE PAGE_CODE = 'CONTACT');

INSERT INTO MH_CMS_PAGE (
    CMS_PAGE_ID, PAGE_CODE, PAGE_TITLE, SLUG, PAGE_TYPE, CONTENT_HTML,
    META_DESCRIPTION, IS_PUBLISHED, SORT_ORDER, CREATED_AT
)
SELECT SEQ_MH_CMS_PAGE_ID.NEXTVAL, 'TERMS', 'Terms and Conditions', 'terms', 'STATIC',
       '<p>By using mamahub.store you agree to our terms of service for online toy purchases in Qatar.</p>',
       'Terms and Conditions', 1, 30, SYSTIMESTAMP FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM MH_CMS_PAGE WHERE PAGE_CODE = 'TERMS');

INSERT INTO MH_CMS_PAGE (
    CMS_PAGE_ID, PAGE_CODE, PAGE_TITLE, SLUG, PAGE_TYPE, CONTENT_HTML,
    META_DESCRIPTION, IS_PUBLISHED, SORT_ORDER, CREATED_AT
)
SELECT SEQ_MH_CMS_PAGE_ID.NEXTVAL, 'PRIVACY', 'Privacy Policy', 'privacy', 'STATIC',
       '<p>We protect your personal data and never sell customer information to third parties.</p>',
       'Privacy Policy', 1, 40, SYSTIMESTAMP FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM MH_CMS_PAGE WHERE PAGE_CODE = 'PRIVACY');

INSERT INTO MH_CMS_PAGE (
    CMS_PAGE_ID, PAGE_CODE, PAGE_TITLE, SLUG, PAGE_TYPE, CONTENT_HTML,
    META_DESCRIPTION, IS_PUBLISHED, SORT_ORDER, CREATED_AT
)
SELECT SEQ_MH_CMS_PAGE_ID.NEXTVAL, 'RETURNS', 'Return Policy', 'returns', 'STATIC',
       '<p>Unopened items in original packaging may be returned within 14 days. Safety-sealed products must remain sealed.</p>',
       'Return Policy', 1, 50, SYSTIMESTAMP FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM MH_CMS_PAGE WHERE PAGE_CODE = 'RETURNS');

COMMIT;
