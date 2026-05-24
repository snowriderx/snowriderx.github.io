/* ================================================================
   Admin Panel — Base JS
   Sidebar toggle, flash auto-dismiss, helpers.
   ================================================================ */

(function () {
  "use strict";

  // ----------------------------------------------------------------
  // Sidebar toggle
  // ----------------------------------------------------------------
  const toggleBtn = document.getElementById("sidebarToggle");
  const sidebar   = document.getElementById("sidebar");
  const mainArea  = document.querySelector(".admin-main");

  if (toggleBtn && sidebar) {
    toggleBtn.addEventListener("click", function () {
      if (window.innerWidth <= 768) {
        sidebar.classList.toggle("open");
      } else {
        sidebar.classList.toggle("collapsed");
        mainArea && mainArea.classList.toggle("expanded");
      }
    });
  }

  // ----------------------------------------------------------------
  // Auto-dismiss flash alerts after 4 s
  // ----------------------------------------------------------------
  document.querySelectorAll(".alert.alert-dismissible").forEach(function (el) {
    setTimeout(function () {
      const bsAlert = bootstrap.Alert.getOrCreateInstance(el);
      bsAlert && bsAlert.close();
    }, 4000);
  });

  // ----------------------------------------------------------------
  // Confirm delete helper
  // Attach data-confirm="message" to any link/button.
  // ----------------------------------------------------------------
  document.addEventListener("click", function (e) {
    const el = e.target.closest("[data-confirm]");
    if (!el) return;
    const msg = el.dataset.confirm || "Bạn có chắc muốn xoá?";
    if (!window.confirm(msg)) {
      e.preventDefault();
      e.stopPropagation();
    }
  });
})();

/* ================================================================
   Batch-list helpers — shared by every admin list page.

   Usage in each list template:
     1. Call initBatchList('sản phẩm') once on DOMContentLoaded
        (or inline in a <script> block after the table).
     2. Batch-delete button: onclick="submitBatchDelete()"
     3. Single-delete button: onclick="confirmDeleteOne(id, name, url)"
     4. Include <form id="deleteOneForm" ...> outside #batchForm.
   ================================================================ */

/**
 * Wire up the select-all checkbox and store the item type label
 * for use by submitBatchDelete / confirmDeleteOne.
 *
 * @param {string} itemType  Singular/plural noun shown in confirm dialogs,
 *                           e.g. "sản phẩm", "banner".
 */
function initBatchList(itemType) {
  window._batchItemType = itemType || "mục";

  const selectAll = document.getElementById("selectAll");
  if (selectAll) {
    selectAll.addEventListener("change", function () {
      document
        .querySelectorAll('input[name="item_id"]')
        .forEach(function (cb) { cb.checked = selectAll.checked; });
    });
  }
}

/**
 * Validate selection, confirm, then submit batchForm with _action=delete.
 * Reads item type from window._batchItemType (set by initBatchList).
 */
function submitBatchDelete() {
  const checked = document.querySelectorAll(
    'input[name="item_id"]:checked'
  ).length;
  if (checked === 0) {
    alert("Bạn phải chọn trước khi nhấn Xóa!");
    return;
  }
  const label = window._batchItemType || "mục";
  if (!confirm("Bạn có muốn xóa " + checked + " " + label + " đã chọn không?")) {
    return;
  }
  document.getElementById("formAction").value = "delete";
  document.getElementById("batchForm").submit();
}

/**
 * Confirm then POST via the shared deleteOneForm (lives outside batchForm
 * to avoid the browser's nested-form restriction).
 *
 * @param {number} id        Record PK shown in the confirm message.
 * @param {string} name      Record name/title shown in the confirm message.
 * @param {string} actionUrl POST target URL for the delete route.
 */
function confirmDeleteOne(id, name, actionUrl) {
  const label = window._batchItemType || "mục";
  if (!confirm("Xóa " + label + " #" + id + " (" + name + ")?")) return;
  const f = document.getElementById("deleteOneForm");
  f.action = actionUrl;
  // Inject CSRF token so Flask-WTF accepts the POST
  var token = document.querySelector('meta[name="csrf-token"]');
  if (token) {
    var inp = f.querySelector('input[name="csrf_token"]');
    if (!inp) {
      inp = document.createElement("input");
      inp.type = "hidden";
      inp.name = "csrf_token";
      f.appendChild(inp);
    }
    inp.value = token.content;
  }
  f.submit();
}
