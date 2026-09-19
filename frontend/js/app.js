/**
 * تطبيق نظام مطابقة بيانات السيارات (Vehicle Data Matching System)
 * كود العميل التفاعلي للربط مع FastAPI
 */

// حالة التطبيق العامة
const state = {
  token: localStorage.getItem("farz_token") || null,
  currentUser: null,
  usersList: [],
  datasetStats: null,
  matchSummary: null,
  currentPage: 1,
  pageSize: 50,
  currentFilter: 'all',
  searchQuery: '',
  selectedDatasetFile: null,
  selectedReferralFile: null
};

// تهيئة التطبيق عند فتح الصفحة
document.addEventListener("DOMContentLoaded", async () => {
  setupEventListeners();
  await loadUsersList();
  await checkAuthAndInitialize();
});

// إعداد مستمعي الأحداث
function setupEventListeners() {
  // تبديل المستخدم من القائمة المنسدلة
  const userSelect = document.getElementById("userSwitcher");
  if (userSelect) {
    userSelect.addEventListener("change", async (e) => {
      const userId = parseInt(e.target.value);
      if (userId) {
        await quickSwitchUser(userId);
      }
    });
  }

  // البحث السريع باللوحة
  const quickSearchBtn = document.getElementById("quickSearchBtn");
  const quickSearchInput = document.getElementById("quickSearchInput");
  if (quickSearchBtn && quickSearchInput) {
    quickSearchBtn.addEventListener("click", performQuickSearch);
    quickSearchInput.addEventListener("keypress", (e) => {
      if (e.key === "Enter") performQuickSearch();
    });
  }

  // فلترة النتائج بالتبويبات
  const tabs = document.querySelectorAll(".tab-btn");
  tabs.forEach(tab => {
    tab.addEventListener("click", () => {
      tabs.forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      state.currentFilter = tab.dataset.filter;
      state.currentPage = 1;
      loadMatchResults();
    });
  });

  // البحث داخل جدول النتائج
  const tableSearchInput = document.getElementById("tableSearchInput");
  if (tableSearchInput) {
    let timeout = null;
    tableSearchInput.addEventListener("input", (e) => {
      clearTimeout(timeout);
      timeout = setTimeout(() => {
        state.searchQuery = e.target.value;
        state.currentPage = 1;
        loadMatchResults();
      }, 300);
    });
  }

  // أزرار التصدير
  const exportXlsxBtn = document.getElementById("exportXlsxBtn");
  const exportCsvBtn = document.getElementById("exportCsvBtn");
  if (exportXlsxBtn) {
    exportXlsxBtn.addEventListener("click", () => triggerExport('xlsx'));
  }
  if (exportCsvBtn) {
    exportCsvBtn.addEventListener("click", () => triggerExport('csv'));
  }

  // السحب والإفلات لملف الإحالة
  setupDropzone("referralDropzone", "referralFileInput", (file) => {
    state.selectedReferralFile = file;
    document.getElementById("referralFileName").innerText = file.name;
    document.getElementById("startMatchBtn").disabled = false;
  });

  // زر بدء مطابقة الإحالة
  const startMatchBtn = document.getElementById("startMatchBtn");
  if (startMatchBtn) {
    startMatchBtn.addEventListener("click", uploadAndMatchReferral);
  }

  // أزرار التنقل بين الصفحات
  const prevPageBtn = document.getElementById("prevPageBtn");
  const nextPageBtn = document.getElementById("nextPageBtn");
  if (prevPageBtn) {
    prevPageBtn.addEventListener("click", () => {
      if (state.currentPage > 1) {
        state.currentPage--;
        loadMatchResults();
      }
    });
  }
  if (nextPageBtn) {
    nextPageBtn.addEventListener("click", () => {
      state.currentPage++;
      loadMatchResults();
    });
  }
}

// تحميل قائمة المستخدمين الـ 50
async function loadUsersList() {
  try {
    const res = await fetch("/api/auth/users");
    const data = await res.json();
    if (data.success) {
      state.usersList = data.users;
      renderUserSwitcher();
    }
  } catch (err) {
    console.error("فشل تحميل قائمة المستخدمين:", err);
  }
}

// عرض قائمة المستخدمين في الـ Dropdown
function renderUserSwitcher() {
  const select = document.getElementById("userSwitcher");
  if (!select) return;

  select.innerHTML = state.usersList.map(u => 
    `<option value="${u.id}">👤 ${u.display_name} (${u.username})</option>`
  ).join("");
}

// التحقق من المصادقة أو التبديل التلقائي للمستخدم الأول
async function checkAuthAndInitialize() {
  if (state.token) {
    try {
      const res = await fetch("/api/auth/me", {
        headers: { "Authorization": `Bearer ${state.token}` }
      });
      if (res.ok) {
        const data = await res.json();
        state.currentUser = data.user;
        updateUserUI();
        await loadDatasetStats();
        return;
      }
    } catch (e) {
      console.warn("رمز المصادقة منتهي أو غير صالح");
    }
  }

  // تسجيل دخول تلقائي إلى المستخدم الأول لتسهيل تجربة الاستخدام الفورية
  if (state.usersList.length > 0) {
    await quickSwitchUser(state.usersList[1]?.id || state.usersList[0].id);
  }
}

// التبديل الفوري للمستخدم
async function quickSwitchUser(userId) {
  try {
    const res = await fetch("/api/auth/quick-switch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId })
    });
    const data = await res.json();
    if (data.success) {
      state.token = data.token;
      state.currentUser = data.user;
      localStorage.setItem("farz_token", data.token);
      updateUserUI();
      showToast(`تم التبديل بنجاح إلى: ${data.user.display_name}`, "success");
      await loadDatasetStats();
      // إعادة ضبط واجهة النتائج
      document.getElementById("resultsSection").style.display = "none";
      state.matchSummary = null;
    }
  } catch (err) {
    showToast("فشل تبديل المستخدم", "error");
  }
}

// تحديث بيانات المستخدم في واجهة الرأس
function updateUserUI() {
  if (!state.currentUser) return;
  const badge = document.getElementById("currentUserBadge");
  const switcher = document.getElementById("userSwitcher");
  if (badge) badge.innerText = state.currentUser.display_name;
  if (switcher) switcher.value = state.currentUser.id;
}

// استرجاع وعرض إحصائيات قاعدة بيانات المستخدم الحالية
async function loadDatasetStats() {
  try {
    const res = await fetch("/api/dataset/stats", {
      headers: { "Authorization": `Bearer ${state.token}` }
    });
    const data = await res.json();
    if (data.success) {
      state.datasetStats = data.stats;
      renderDatasetStats();
    }
  } catch (err) {
    console.error("فشل استرجاع إحصائيات البيانات:", err);
  }
}

function renderDatasetStats() {
  const stats = state.datasetStats;
  const statusTag = document.getElementById("datasetStatusTag");
  const totalRecs = document.getElementById("statTotalRecords");
  const distinctPlates = document.getElementById("statDistinctPlates");
  const dupsCount = document.getElementById("statDuplicatePlates");
  const lastUpdate = document.getElementById("statLastUpdated");

  if (!stats || !stats.exists || stats.total_records === 0) {
    if (statusTag) {
      statusTag.className = "status-tag empty";
      statusTag.innerText = "⚠️ لا توجد بيانات محملة لهذا المستخدم";
    }
    if (totalRecs) totalRecs.innerText = "0";
    if (distinctPlates) distinctPlates.innerText = "0";
    if (dupsCount) dupsCount.innerText = "0";
    if (lastUpdate) lastUpdate.innerText = "لم يتم الرفع بعد";
  } else {
    if (statusTag) {
      statusTag.className = "status-tag active";
      statusTag.innerText = "✅ قاعدة بيانات نشطة وجاهزة";
    }
    if (totalRecs) totalRecs.innerText = Number(stats.total_records).toLocaleString();
    if (distinctPlates) distinctPlates.innerText = Number(stats.distinct_plates).toLocaleString();
    if (dupsCount) dupsCount.innerText = Number(stats.duplicate_plates_count).toLocaleString();
    if (lastUpdate) lastUpdate.innerText = `${stats.last_updated || 'اليوم'} (${stats.file_size_mb} ميغابايت)`;
  }
}

// نافذة رفع واستبدال البيانات اليومية (2M سجل)
function openUploadModal() {
  document.getElementById("uploadModal").classList.add("open");
}

function closeUploadModal() {
  document.getElementById("uploadModal").classList.remove("open");
  state.selectedDatasetFile = null;
  document.getElementById("datasetFileName").innerText = "";
  document.getElementById("uploadDatasetBtn").disabled = true;
  document.getElementById("datasetProgressBar").style.display = "none";
}

// تنفيذ رفع ملف بيانات السيارات
async function uploadDatasetFile() {
  const fileInput = document.getElementById("datasetFileInput");
  const file = state.selectedDatasetFile || (fileInput ? fileInput.files[0] : null);
  if (!file) {
    showToast("يرجى اختيار ملف البيانات أولاً", "error");
    return;
  }

  const formData = new FormData();
  formData.append("file", file);

  const btn = document.getElementById("uploadDatasetBtn");
  const progressBar = document.getElementById("datasetProgressBar");
  const progressFill = document.getElementById("datasetProgressFill");
  const statusMsg = document.getElementById("datasetUploadMsg");

  btn.disabled = true;
  btn.innerText = "جاري الرفع والمعالجة...";
  progressBar.style.display = "block";
  progressFill.style.width = "45%";
  statusMsg.innerText = "جاري قراءة البيانات وبناء الفهارس (قد يستغرق بضع ثوانٍ للملفات الضخمة)...";

  try {
    const res = await fetch("/api/dataset/upload", {
      method: "POST",
      headers: { "Authorization": `Bearer ${state.token}` },
      body: formData
    });

    const data = await res.json();
    progressFill.style.width = "100%";

    if (res.ok && data.success) {
      showToast(data.message, "success");
      await loadDatasetStats();
      setTimeout(() => {
        closeUploadModal();
        btn.innerText = "بدء رفع واستبدال البيانات";
      }, 1000);
    } else {
      showToast(data.detail || "فشل رفع الملف", "error");
      btn.disabled = false;
      btn.innerText = "إعادة المحاولة";
    }
  } catch (err) {
    showToast("حدث خطأ في الاتصال أثناء الرفع", "error");
    btn.disabled = false;
    btn.innerText = "إعادة المحاولة";
  }
}

// تفريغ بيانات المستخدم
async function confirmClearDataset() {
  if (!confirm("هل أنت متأكد من تفريغ قاعدة بيانات هذا المستخدم بالكامل؟")) return;
  try {
    const res = await fetch("/api/dataset/clear", {
      method: "POST",
      headers: { "Authorization": `Bearer ${state.token}` }
    });
    const data = await res.json();
    if (data.success) {
      showToast("تم تفريغ البيانات بنجاح", "success");
      await loadDatasetStats();
    }
  } catch (err) {
    showToast("فشل تفريغ البيانات", "error");
  }
}

// رفع ملف الإحالة والبدء في المطابقة الفورية
async function uploadAndMatchReferral() {
  const file = state.selectedReferralFile;
  if (!file) {
    showToast("يرجى اختيار ملف الإحالة أولاً", "error");
    return;
  }

  if (!state.datasetStats || state.datasetStats.total_records === 0) {
    showToast("تنبيه: قاعدة بيانات السيارات فارغة! يرجى رفع ملف السيارات أولاً.", "error");
  }

  const formData = new FormData();
  formData.append("file", file);

  const btn = document.getElementById("startMatchBtn");
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner"></span> جاري المطابقة الفورية...`;

  try {
    const res = await fetch("/api/referral/match", {
      method: "POST",
      headers: { "Authorization": `Bearer ${state.token}` },
      body: formData
    });

    const data = await res.json();
    btn.disabled = false;
    btn.innerHTML = `⚡ بدء المطابقة الفورية الآن`;

    if (res.ok && data.success) {
      state.matchSummary = data.summary;
      renderMatchBanner();
      state.currentPage = 1;
      await loadMatchResults();
      document.getElementById("resultsSection").style.display = "block";
      document.getElementById("resultsSection").scrollIntoView({ behavior: 'smooth' });
      showToast(`تمت المطابقة بنجاح في ${data.summary.execution_time_ms} ميلي ثانية!`, "success");
    } else {
      showToast(data.detail || "فشل تنفيذ المطابقة", "error");
    }
  } catch (err) {
    btn.disabled = false;
    btn.innerHTML = `⚡ بدء المطابقة الفورية الآن`;
    showToast("حدث خطأ أثناء الاتصال بالسيرفر للمطابقة", "error");
  }
}

// عرض بطاقة إحصائيات المطابقة
function renderMatchBanner() {
  const s = state.matchSummary;
  if (!s) return;

  document.getElementById("sumTotalRef").innerText = Number(s.total_referrals).toLocaleString();
  document.getElementById("sumMatchedRef").innerText = Number(s.matched_referrals).toLocaleString();
  document.getElementById("sumUnmatchedRef").innerText = Number(s.unmatched_referrals).toLocaleString();
  document.getElementById("sumTotalVehicles").innerText = Number(s.total_vehicle_matches).toLocaleString();
  document.getElementById("sumTimeMs").innerText = `${s.execution_time_ms} ms`;
}

// تحميل وعرض جدول النتائج الشامل لكافة الأعمدة
async function loadMatchResults() {
  const tableBody = document.getElementById("resultsTableBody");
  if (!tableBody) return;

  tableBody.innerHTML = `<tr><td colspan="15" style="text-align:center; padding: 24px;">جاري تحميل كافة بيانات ومطابقات الملفين...</td></tr>`;

  try {
    const query = new URLSearchParams({
      page: state.currentPage,
      page_size: state.pageSize,
      filter_status: state.currentFilter,
      search: state.searchQuery
    });

    const res = await fetch(`/api/referral/results?${query.toString()}`, {
      headers: { "Authorization": `Bearer ${state.token}` }
    });

    const data = await res.json();
    if (data.success) {
      state.columns = data.data.columns || [];
      renderTableHeaders(state.columns);
      renderTableRows(data.data.records, state.columns);
      renderPagination(data.data);
    }
  } catch (err) {
    tableBody.innerHTML = `<tr><td colspan="15" style="text-align:center; color: red;">فشل استعراض النتائج</td></tr>`;
  }
}

// رسم رؤوس الأعمدة ديناميكيًا لشمول كل حقول الإحالة والسيارة
function renderTableHeaders(columns) {
  const thead = document.getElementById("resultsTableHead");
  if (!thead) return;

  if (!columns || columns.length === 0) {
    thead.innerHTML = "";
    return;
  }

  const ths = columns.map(col => {
    let extraClass = "";
    let cleanTitle = col;
    if (col === "حالة المطابقة") {
      extraClass = "th-status sticky-col";
      cleanTitle = "حالة المطابقة";
    } else if (col.startsWith("[الإحالة]")) {
      extraClass = "th-referral";
      const name = col.replace(/^\[الإحالة\]\s*/, '');
      cleanTitle = `<span class="col-pill pill-ref">الإحالة</span> ${name}`;
    } else if (col.startsWith("[السيارة]")) {
      extraClass = "th-vehicle";
      const name = col.replace(/^\[السيارة\]\s*/, '');
      cleanTitle = `<span class="col-pill pill-veh">الداتا</span> ${name}`;
    }
    return `<th class="${extraClass}">${cleanTitle}</th>`;
  }).join("");

  thead.innerHTML = `<tr><th style="width: 45px; text-align:center;">#</th>${ths}</tr>`;
}

// رسم صفوف جدول النتائج بكافة الأعمدة
function renderTableRows(records, columns) {
  const tableBody = document.getElementById("resultsTableBody");
  if (!tableBody) return;

  if (!records || records.length === 0) {
    const colCount = (columns ? columns.length : 10) + 1;
    tableBody.innerHTML = `<tr><td colspan="${colCount}" style="text-align:center; padding: 32px; color: var(--text-muted);">لا توجد سجلات مطابقة لهذا البحث أو الفلتر.</td></tr>`;
    return;
  }

  tableBody.innerHTML = records.map((r, idx) => {
    const rowNum = (state.currentPage - 1) * state.pageSize + idx + 1;

    const tds = columns.map(col => {
      const val = r[col];
      const hasVal = (val !== null && val !== undefined && val !== '');
      const valStr = hasVal ? String(val) : '<span style="color:#cbd5e1">-</span>';

      if (col === "حالة المطابقة") {
        let badgeClass = "badge-matched";
        if (val === "غير متطابق") badgeClass = "badge-unmatched";
        else if (val === "تطابق متعدد") badgeClass = "badge-multiple";
        return `<td class="sticky-col"><span class="badge ${badgeClass}">${val}</span></td>`;
      }

      let contentHtml = valStr;
      if (hasVal) {
        const rawStr = String(val).trim();
        if (rawStr.startsWith('http://') || rawStr.startsWith('https://') || rawStr.includes('maps.google') || rawStr.includes('goo.gl')) {
          contentHtml = `<a href="${encodeURI(rawStr)}" target="_blank" rel="noopener noreferrer" class="map-link-btn" title="${rawStr}">📍 فتح الموقع</a>`;
        } else if ((col.includes('موقع') || col.includes('رابط') || col.includes('خريطة') || col.includes('location')) && rawStr.includes(',') && !isNaN(parseFloat(rawStr.split(',')[0]))) {
          contentHtml = `<a href="https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(rawStr)}" target="_blank" rel="noopener noreferrer" class="map-link-btn" title="${rawStr}">📍 فتح الخريطة</a>`;
        }
      }

      // تمييز خفيف بين أعمدة الإحالة وأعمدة الداتا
      const cellClass = col.startsWith("[السيارة]") ? "td-veh" : "td-ref";
      return `<td class="${cellClass}">${contentHtml}</td>`;
    }).join("");

    return `<tr><td style="text-align:center; font-weight:700; color:#64748b;">${rowNum}</td>${tds}</tr>`;
  }).join("");
}

// رسم أزرار التنقل
function renderPagination(pageData) {
  const info = document.getElementById("paginationInfo");
  const prevBtn = document.getElementById("prevPageBtn");
  const nextBtn = document.getElementById("nextPageBtn");

  if (info) {
    info.innerText = `عرض الصفحة ${pageData.page} من إجمالي ${pageData.pages} (إجمالي السجلات: ${Number(pageData.total).toLocaleString()})`;
  }
  if (prevBtn) prevBtn.disabled = pageData.page <= 1;
  if (nextBtn) nextBtn.disabled = pageData.page >= pageData.pages;
}

// تصدير النتائج
function triggerExport(format) {
  const query = new URLSearchParams({
    format: format,
    filter_status: state.currentFilter
  });
  window.location.href = `/api/referral/export?${query.toString()}`;
  showToast(`جاري تجهيز وتحميل ملف الـ ${format.toUpperCase()} الشامل لكافة البيانات...`, "info");
}

// تنفيذ البحث السريع المنفرد عن لوحة مع عرض كافة أعمدة السيارة
async function performQuickSearch() {
  const input = document.getElementById("quickSearchInput");
  const plate = input ? input.value.trim() : "";
  if (!plate) {
    showToast("يرجى كتابة رقم اللوحة للبحث", "warning");
    return;
  }

  const resContainer = document.getElementById("quickSearchResults");
  resContainer.innerHTML = "<p style='padding:10px; color:#64748b;'>جاري البحث الفوري في 2 مليون سيارة...</p>";
  resContainer.style.display = "block";

  try {
    const res = await fetch("/api/dataset/quick-search", {
      method: "POST",
      headers: { 
        "Content-Type": "application/json",
        "Authorization": `Bearer ${state.token}` 
      },
      body: JSON.stringify({ plate: plate })
    });

    const data = await res.json();
    if (data.success) {
      if (data.results.length === 0) {
        resContainer.innerHTML = `
          <div style="background:#fee2e2; color:#b91c1c; padding:12px; border-radius:8px; font-size:13px;">
            ❌ اللوحة <strong>"${plate}"</strong> غير موجودة في قاعدة بيانات هذا المستخدم.
          </div>
        `;
      } else {
        const rows = data.results.map((v, i) => {
          const fields = Object.entries(v).map(([key, val]) => {
            const cleanKey = key.replace('[السيارة] ', '');
            return `<div><strong style="color:#475569;">${cleanKey}:</strong> <span style="color:#0f172a; font-weight:600;">${val || '-'}</span></div>`;
          }).join("");

          return `
            <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:12px; margin-bottom:8px;">
              <div style="display:flex; justify-content:space-between; margin-bottom:8px; border-bottom:1px dashed #cbd5e1; padding-bottom:6px;">
                <span style="font-weight:700; color:#1e293b;">مركبة #${i + 1}</span>
                <span class="badge badge-matched">متطابق</span>
              </div>
              <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); font-size:12px; gap:8px;">
                ${fields}
              </div>
            </div>
          `;
        }).join("");

        resContainer.innerHTML = `
          <div style="margin-bottom:8px; font-weight:700; color:#15803d; font-size:13px;">
            ✅ تم العثور على ${data.results.length} تطابق(ات) للوحة مع كافة بياناتها:
          </div>
          ${rows}
        `;
      }
    }
  } catch (err) {
    resContainer.innerHTML = "<p style='color:red; padding:10px;'>فشل تنفيذ البحث السريع</p>";
  }
}

// مساعد إعداد منطقة السحب والإفلات
function setupDropzone(dropzoneId, inputId, onFileSelect) {
  const dropzone = document.getElementById(dropzoneId);
  const input = document.getElementById(inputId);
  if (!dropzone || !input) return;

  dropzone.addEventListener("click", () => input.click());

  dropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropzone.classList.add("dragover");
  });

  dropzone.addEventListener("dragleave", () => {
    dropzone.classList.remove("dragover");
  });

  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
    if (e.dataTransfer.files.length > 0) {
      onFileSelect(e.dataTransfer.files[0]);
    }
  });

  input.addEventListener("change", () => {
    if (input.files.length > 0) {
      onFileSelect(input.files[0]);
    }
  });
}

// إظهار إشعار Toast سريع
function showToast(message, type = "info") {
  let container = document.getElementById("toastContainer");
  if (!container) {
    container = document.createElement("div");
    container.id = "toastContainer";
    container.className = "toast-container";
    document.body.appendChild(container);
  }

  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.innerText = message;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = "0";
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}
