-- Arabic display name for ERP CATEGORY rows (main / dept / micro).
-- Applied automatically by Nova ensure_category_nameara_column() when missing.
-- Safe to run manually on Oracle if preferred.

ALTER TABLE CATEGORY ADD NAMEARA VARCHAR2(100);
