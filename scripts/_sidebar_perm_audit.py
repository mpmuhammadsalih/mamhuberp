"""Find sidebar url_for links without nearby has_menu_permission guard."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
base = (ROOT / "templates" / "base.html").read_text(encoding="utf-8")
start = base.find('class="sidebar"')
if start < 0:
    start = 0
end = base.find("</aside>", start)
chunk = base[start:end] if end > start else base
lines = chunk.splitlines()
for i, line in enumerate(lines):
    if "url_for" not in line:
        continue
    window = "\n".join(lines[max(0, i - 3) : i + 2])
    if "has_menu_permission" in window or "has_any_menu_permission" in window:
        continue
    if "allow_all_permissions" in window:
        continue
    if "{% if" not in window and "{% elif" not in window:
        print(f"line~{i}: {line.strip()[:140]}")
