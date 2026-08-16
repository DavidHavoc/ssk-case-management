(() => {
  const sidebar = document.querySelector("#primary-sidebar");
  const toggle = document.querySelector(".mobile-nav-toggle");
  const backdrop = document.querySelector(".nav-backdrop");
  const pageTitle = document.querySelector(".topbar-title");
  const mainHeading = document.querySelector("#main-content h1");
  const mobileViewport = window.matchMedia("(max-width: 64rem)");

  if (pageTitle && mainHeading) {
    pageTitle.textContent = mainHeading.textContent.trim();
  }

  document.addEventListener("submit", (event) => {
    const confirmation = event.submitter?.dataset.confirm;
    if (confirmation && !window.confirm(confirmation)) {
      event.preventDefault();
    }
  });

  if (!sidebar || !toggle || !backdrop) {
    return;
  }

  const setNavigationOpen = (open, restoreFocus = false) => {
    sidebar.classList.toggle("is-open", open);
    toggle.setAttribute("aria-expanded", String(open));
    backdrop.hidden = !open;
    document.body.classList.toggle("nav-open", open);
    if (open) {
      sidebar.querySelector("a")?.focus();
    } else if (restoreFocus) {
      toggle.focus();
    }
  };

  toggle.addEventListener("click", () => {
    setNavigationOpen(toggle.getAttribute("aria-expanded") !== "true");
  });
  backdrop.addEventListener("click", () => setNavigationOpen(false, true));
  sidebar.addEventListener("click", (event) => {
    if (mobileViewport.matches && event.target.closest("a")) {
      setNavigationOpen(false);
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && sidebar.classList.contains("is-open")) {
      setNavigationOpen(false, true);
    }
    if (event.key === "Escape") {
      document.querySelectorAll("details[open]").forEach((detail) => {
        detail.open = false;
      });
    }
  });
  mobileViewport.addEventListener("change", (event) => {
    if (!event.matches) {
      setNavigationOpen(false);
    }
  });
})();
