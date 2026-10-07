/** Wrap each submenu link (real URL) with row + “open in new tab” icon. Idempotent. */
function enhanceSubmenuNewTabIcons() {
  document.querySelectorAll(".sidebar__submenu").forEach((submenu) => {
    Array.from(submenu.children).forEach((child) => {
      if (!child || child.tagName !== "A") return;
      const a = child;
      if (a.closest(".sidebar__submenu-item")) return;

      const hrefRaw = (a.getAttribute("href") || "").trim();
      const hrefUpper = hrefRaw.toUpperCase();
      if (!hrefRaw || hrefRaw === "#" || hrefUpper.startsWith("JAVASCRIPT:")) return;

      const wrap = document.createElement("div");
      wrap.className = "sidebar__submenu-item";
      a.parentNode.insertBefore(wrap, a);
      wrap.appendChild(a);

      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "sidebar__submenu-newtab";
      btn.setAttribute("aria-label", "Open in new tab");
      btn.setAttribute("title", "Open in new tab");
      btn.innerHTML = '<i class="bi bi-box-arrow-up-right" aria-hidden="true"></i>';
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        window.open(a.href, "_blank", "noopener,noreferrer");
      });
      wrap.appendChild(btn);
    });
  });
}

function initSidebar() {
  if (window.__nexaSidebarInited) return;
  const sidebar = document.getElementById("sidebar");
  const layout = document.querySelector(".layout");
  if (!sidebar || !layout) return;
  window.__nexaSidebarInited = true;

  try {
    enhanceSubmenuNewTabIcons();
  } catch (_) {
    /* submenu decoration must not block menu */
  }

  const closeAllSubmenus = () => {
    document.querySelectorAll(".sidebar__submenu.is-open").forEach((submenu) => {
      submenu.classList.remove("is-open");
    });
  };

  const collapseSidebar = () => {
    sidebar.classList.add("collapsed");
    layout.classList.add("sidebar-collapsed");
  };

  const toggleSection = (section) => {
    const target = section.dataset.menu;
    const submenu = document.getElementById(target);
    if (!submenu) return;
    if (sidebar.classList.contains("collapsed")) {
      sidebar.classList.remove("collapsed");
      layout.classList.remove("sidebar-collapsed");
    }
    submenu.classList.toggle("is-open");
  };

  document.querySelectorAll(".sidebar__section").forEach((section) => {
    section.addEventListener("click", () => toggleSection(section));
  });

  document.querySelectorAll(".sidebar__menu a").forEach((link) => {
    link.addEventListener("click", () => {
      closeAllSubmenus();
      collapseSidebar();
    });
  });

  closeAllSubmenus();
  collapseSidebar();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initSidebar);
} else {
  initSidebar();
}
