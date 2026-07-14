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

    element.querySelectorAll(".map-marker").forEach((marker) => marker.remove());
    const map = window.L.map(element, { scrollWheelZoom: true, zoomControl: true });
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

    function renderPlacePreview(item) {
      const preview = document.querySelector("#place-preview");
      if (!preview || !item) return;
      preview.replaceChildren();

      const heading = document.createElement("div");
      heading.className = "place-preview-head";
      const title = document.createElement("h3");
      title.id = "place-preview-title";
      title.textContent = item.place?.name || item.title || "收藏地點";
      heading.appendChild(title);
      const category = item.place?.category || "地點";
      const categoryText = document.createElement("span");
      categoryText.textContent = category;
      heading.appendChild(categoryText);
      preview.appendChild(heading);

      const facts = Array.isArray(item.place_facts) ? item.place_facts : [];
      if (facts.length) {
        const list = document.createElement("dl");
        list.className = "place-preview-facts";
        facts.forEach((fact) => {
          if (!fact || !fact.label || !fact.value) return;
          const row = document.createElement("div");
          const label = document.createElement("dt");
          label.textContent = fact.label;
          const value = document.createElement("dd");
          value.textContent = fact.value;
          row.append(label, value);
          list.appendChild(row);
        });
        preview.appendChild(list);
      } else {
        const empty = document.createElement("p");
        empty.className = "place-preview-empty-copy";
        empty.textContent = "這筆地點目前還沒有補上評價、地址或營業資訊。";
        preview.appendChild(empty);
      }

      const actions = document.createElement("div");
      actions.className = "place-preview-actions";
      if (item.place_url || item.url) {
        const detail = document.createElement("a");
        detail.href = item.place_url || item.url;
        detail.textContent = "查看完整地點";
        actions.appendChild(detail);
      }
      if (actions.childElementCount) preview.appendChild(actions);
    }

    const selectSource = (sourceId, focusList) => {
      document.querySelectorAll("[data-place-source-id]").forEach((row) => {
        row.classList.toggle("is-selected", row.dataset.placeSourceId === sourceId);
      });
      const selected = points.find((point) => point.item?.source_id === sourceId);
      if (selected) renderPlacePreview(selected.item || {});
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
