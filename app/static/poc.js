// Tabs, drag-and-drop highlight and chosen-file names. No inline scripts (CSP).
(function () {
  function show(name) {
    document.querySelectorAll(".tab").forEach(function (t) {
      var on = t.dataset.tab === name;
      t.classList.toggle("active", on);
      t.setAttribute("aria-selected", on);
    });
    document.querySelectorAll(".panel").forEach(function (p) {
      p.hidden = p.id !== "panel-" + name;
    });
    try { history.replaceState(null, "", "#" + name); } catch (e) {}
  }
  document.addEventListener("click", function (e) {
    var t = e.target.closest(".tab");
    if (t) show(t.dataset.tab);
  });
  document.addEventListener("change", function (e) {
    if (!e.target.matches(".drop input")) return;
    var names = Array.from(e.target.files).map(function (f) { return f.name; });
    e.target.closest(".drop").querySelector(".drop-names").textContent =
      names.length > 3 ? names.length + " files selected" : names.join(", ");
  });
  ["dragenter", "dragover"].forEach(function (ev) {
    document.addEventListener(ev, function (e) {
      var d = e.target.closest && e.target.closest(".drop");
      if (d) d.classList.add("over");
    });
  });
  ["dragleave", "drop"].forEach(function (ev) {
    document.addEventListener(ev, function (e) {
      var d = e.target.closest && e.target.closest(".drop");
      if (d) d.classList.remove("over");
    });
  });
  document.addEventListener("DOMContentLoaded", function () {
    if (location.hash === "#dup") show("dup");
  });
})();
