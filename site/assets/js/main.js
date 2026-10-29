/* 基督教世界新闻 · 前端交互
   首页：热门地区/主题点击筛选 + 按日期导航
   分类页：标题/来源搜索
*/
(function () {
  "use strict";

  // ---------- 首页 ----------
  function initHome() {
    var cards = Array.prototype.slice.call(document.querySelectorAll(".article-card"));
    if (!cards.length) return;

    var filterBar = document.getElementById("filter-bar");
    var filterLabel = document.getElementById("filter-label");
    var filterCount = document.getElementById("filter-count");
    var clearBtn = document.getElementById("clear-filter");
    var calData = null;
    try { calData = JSON.parse(document.getElementById("calendar-data").textContent || "{}"); } catch (e) { calData = {}; }

    function applyFilter(keyword) {
      keyword = (keyword || "").trim().toLowerCase();
      if (!keyword) { clearFilter(); return; }
      var shown = 0;
      cards.forEach(function (card) {
        var text = card.textContent.toLowerCase();
        var hit = text.indexOf(keyword) !== -1;
        card.style.display = hit ? "" : "none";
        if (hit) shown++;
      });
      filterLabel.textContent = keyword;
      filterCount.textContent = shown;
      filterBar.hidden = false;
    }

    function clearFilter() {
      cards.forEach(function (card) { card.style.display = ""; });
      filterBar.hidden = true;
    }

    if (clearBtn) clearBtn.addEventListener("click", clearFilter);

    document.querySelectorAll(".hot-item, .topic-tag").forEach(function (el) {
      function trigger() { applyFilter(el.getAttribute("data-filter")); }
      el.addEventListener("click", trigger);
      el.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") trigger(); });
    });

    // 日期导航：仅显示选中日期段
    var dateSections = Array.prototype.slice.call(document.querySelectorAll(".date-section"));
    var datePrev = document.getElementById("date-prev");
    var dateNext = document.getElementById("date-next");
    var dateAll = document.getElementById("date-all");
    var dateTitle = document.getElementById("date-nav-title");
    var navIndex = 0; // 0 = 全部
    function renderNav() {
      if (navIndex === 0) {
        dateSections.forEach(function (s) { s.style.display = ""; });
        dateTitle.textContent = "全部日期";
        if (datePrev) datePrev.disabled = false;
        if (dateNext) dateNext.disabled = false;
        return;
      }
      var sel = dateSections[navIndex - 1];
      dateSections.forEach(function (s) { s.style.display = s === sel ? "" : "none"; });
      dateTitle.textContent = (sel.id || "").replace("date-", "");
    }
    if (datePrev) datePrev.addEventListener("click", function () {
      navIndex = Math.max(0, navIndex - 1); renderNav();
    });
    if (dateNext) dateNext.addEventListener("click", function () {
      navIndex = Math.min(dateSections.length, navIndex + 1); renderNav();
    });
    if (dateAll) dateAll.addEventListener("click", function () {
      navIndex = 0; renderNav();
    });
    renderNav();
  }

  // ---------- 分类页 ----------
  function initCategory() {
    var input = document.getElementById("filter-input");
    var select = document.getElementById("source-filter");
    var list = document.getElementById("article-list");
    if (!list) return;
    var cards = Array.prototype.slice.call(list.querySelectorAll(".article-card"));

    function apply() {
      var kw = (input.value || "").trim().toLowerCase();
      var src = (select.value || "").trim();
      cards.forEach(function (card) {
        var text = card.textContent.toLowerCase();
        var okText = !kw || text.indexOf(kw) !== -1;
        var okSrc = !src || card.getAttribute("data-source") === src;
        card.style.display = (okText && okSrc) ? "" : "none";
      });
    }
    if (input) input.addEventListener("input", apply);
    if (select) select.addEventListener("change", apply);
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (document.querySelector(".home-layout")) initHome();
    if (document.getElementById("article-list")) initCategory();
  });
})();
