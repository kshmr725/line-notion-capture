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

  function initFoodMap(element) {
    if (!element) return;
    let points = [];
    try {
      points = JSON.parse(element.dataset.mapPoints || "[]");
    } catch (_error) {
      points = [];
    }
    if (!Array.isArray(points) || !points.length || !window.L) return;

    const map = window.L.map(element, { scrollWheelZoom: false, zoomControl: true });
    window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map);

    const markers = new Map();
    const pinIcon = window.L.divIcon({
      className: "portal-map-pin",
      html: "<span></span>",
      iconSize: [24, 24],
      iconAnchor: [12, 22],
    });
    const bounds = [];

    const selectSource = (sourceId, focusList) => {
      document.querySelectorAll("[data-place-source-id]").forEach((row) => {
        row.classList.toggle("is-selected", row.dataset.placeSourceId === sourceId);
      });
      markers.forEach((marker, key) => {
        const node = marker.getElement();
        if (node) node.classList.toggle("is-selected", key === sourceId);
      });
      if (focusList) {
        const row = document.querySelector(`[data-place-source-id="${CSS.escape(sourceId)}"]`);
        if (row) row.focus({ preventScroll: true });
      }
      element.dispatchEvent(new CustomEvent("brain-cloud:place-selected", {
        bubbles: true,
        detail: { sourceId },
      }));
    };

    points.forEach((point) => {
      const latitude = Number(point.latitude);
      const longitude = Number(point.longitude);
      const item = point.item || {};
      if (!Number.isFinite(latitude) || !Number.isFinite(longitude) || !item.source_id) return;
      const marker = window.L.marker([latitude, longitude], { icon: pinIcon, title: item.title || "收藏地點" }).addTo(map);
      marker.bindPopup(`<strong>${escapeHtml(item.title || "收藏地點")}</strong>`);
      marker.on("click", () => selectSource(item.source_id, true));
      markers.set(item.source_id, marker);
      bounds.push([latitude, longitude]);
    });
    if (bounds.length > 1) map.fitBounds(bounds, { padding: [28, 28] });
    else if (bounds.length === 1) map.setView(bounds[0], 14);

    document.querySelectorAll("[data-place-source-id]").forEach((row) => {
      row.addEventListener("click", () => selectSource(row.dataset.placeSourceId, false));
      row.addEventListener("keydown", (event) => {
        if (event.key === " ") {
          event.preventDefault();
          selectSource(row.dataset.placeSourceId, false);
        }
      });
    });
    element.dataset.mapReady = "true";
  }

  function escapeHtml(value) {
    return String(value).replace(/[&<>'"]/g, (character) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
    }[character]));
  }

  window.initFoodMap = initFoodMap;
  window.addEventListener("DOMContentLoaded", () => {
    const map = document.querySelector("#food-map[data-map-points]");
    if (map) initFoodMap(map);
  });
})();
