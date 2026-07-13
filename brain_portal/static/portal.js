(() => {
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
