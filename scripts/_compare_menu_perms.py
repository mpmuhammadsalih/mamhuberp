"""Compare base.html menu_path refs vs permissions.MENU_GROUPS (runtime)."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from permissions import MENU_GROUPS  # noqa: E402

base = (ROOT / "templates" / "base.html").read_text(encoding="utf-8")
base_paths = set(re.findall(r"has_menu_permission\('([^']+)'\)", base))
for block in re.findall(r"has_any_menu_permission\(\[([^\]]+)\]", base, re.DOTALL):
    base_paths.update(re.findall(r"'([^']+)'", block))

perm_paths = set()
for g in MENU_GROUPS:
    for it in g.get("items", []):
        if isinstance(it, dict) and it.get("menu_path"):
            perm_paths.add(str(it["menu_path"]))

missing = sorted(base_paths - perm_paths)
print(f"In base.html but NOT in MENU_GROUPS ({len(missing)}):")
for p in missing:
    print(f"  {p}")
