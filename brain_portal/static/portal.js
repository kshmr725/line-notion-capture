(() => {
  const toggleFilter = (control) => {
    const isPressed = control.getAttribute("aria-pressed") === "true";
    control.setAttribute("aria-pressed", String(!isPressed));
  };

  document.querySelectorAll("[data-filter]").forEach((control) => {
    control.addEventListener("click", () => toggleFilter(control));
    control.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        toggleFilter(control);
      }
    });
  });

  document.querySelectorAll("[data-search-form]").forEach((form) => {
    form.addEventListener("submit", () => {
      const status = form.querySelector("[data-search-status]");
      form.setAttribute("aria-busy", "true");
      if (status) {
        status.textContent = form.dataset.loadingCopy;
      }
    });
  });
})();
