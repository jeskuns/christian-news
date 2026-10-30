/* 基督教世界新闻 · 前端交互
   首页：热门地区/主题点击筛选 + 按日期导航 + 只看福音派来源
   分类页：标题/来源搜索 + 隐藏需留意的来源/争议
*/
(function () {
  "use strict";
  var FLAGGED_STANCES = ["catholic", "orthodox", "mainline"];

  // 移动端汉堡菜单
  (function () {
    var navToggle = document.getElementById("navToggle");
    var mainNav = document.getElementById("mainNav");
    if (!navToggle || !mainNav) return;
    navToggle.addEventListener("click", function () {
      var open = mainNav.classList.toggle("open");
      navToggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
    mainNav.addEventListener("click", function (e) {
      if (e.target && e.target.tagName === "A") {
        mainNav.classList.remove("open");
        navToggle.setAttribute("aria-expanded", "false");
      }
    });
  })();

  function isFlagged(card) {
    var st = card.getAttribute("data-stance") || "";
    var fl = card.getAttribute("data-flags") || "";
    return FLAGGED_STANCES.indexOf(st) !== -1 || fl.length > 0;
  }

  // ---------- 首页 ----------
  function initHome() {
    var cards = Array.prototype.slice.call(document.querySelectorAll(".article-card"));
    if (!cards.length) return;

    var filterBar = document.getElementById("filter-bar");
    var filterLabel = document.getElementById("filter-label");
    var filterCount = document.getElementById("filter-count");
    var clearBtn = document.getElementById("clear-filter");
    var hideFlagged = document.getElementById("hide-flagged");
    var currentKw = "";

    function apply() {
      var kw = currentKw.trim().toLowerCase();
      var hide = hideFlagged && hideFlagged.checked;
      var shown = 0;
      cards.forEach(function (card) {
        var textOk = !kw || card.textContent.toLowerCase().indexOf(kw) !== -1;
        var flagOk = !hide || !isFlagged(card);
        var vis = textOk && flagOk;
        card.style.display = vis ? "" : "none";
        if (vis) shown++;
      });
      if (kw) {
        filterLabel.textContent = kw;
        filterCount.textContent = shown;
        filterBar.hidden = false;
      } else {
        filterBar.hidden = true;
      }
    }

    function applyFilter(keyword) { currentKw = keyword; apply(); }
    function clearFilter() { currentKw = ""; apply(); }

    if (clearBtn) clearBtn.addEventListener("click", clearFilter);
    if (hideFlagged) hideFlagged.addEventListener("change", apply);

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
      navIndex = Math.max(0, navIndex - 1); renderNav(); apply();
    });
    if (dateNext) dateNext.addEventListener("click", function () {
      navIndex = Math.min(dateSections.length, navIndex + 1); renderNav(); apply();
    });
    if (dateAll) dateAll.addEventListener("click", function () {
      navIndex = 0; renderNav(); apply();
    });
    renderNav();
    apply();
  }

  // ---------- 分类页 ----------
  function initCategory() {
    var input = document.getElementById("filter-input");
    var select = document.getElementById("source-filter");
    var hideFlagged = document.getElementById("hide-flagged");
    var list = document.getElementById("article-list");
    if (!list) return;
    var cards = Array.prototype.slice.call(list.querySelectorAll(".article-card"));

    function apply() {
      var kw = (input.value || "").trim().toLowerCase();
      var src = (select.value || "").trim();
      var hide = hideFlagged && hideFlagged.checked;
      cards.forEach(function (card) {
        var text = card.textContent.toLowerCase();
        var okText = !kw || text.indexOf(kw) !== -1;
        var okSrc = !src || card.getAttribute("data-source") === src;
        var flagOk = !hide || !isFlagged(card);
        card.style.display = (okText && okSrc && flagOk) ? "" : "none";
      });
    }
    if (input) input.addEventListener("input", apply);
    if (select) select.addEventListener("change", apply);
    if (hideFlagged) hideFlagged.addEventListener("change", apply);
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (document.querySelector(".home-layout")) initHome();
    if (document.getElementById("article-list")) initCategory();
  });
})();
