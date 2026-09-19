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
  selectedReferralFile: null,
  selectedReferralFiles: [],
  lastRecords: [],
  // متغيرات خريطة أسطول السيارات والتتبع والملاحة
  fleetMap: null,
  markersLayer: null,
  userGpsMarker: null,
  routePolyline: null,
  userLocation: null,
  mapPoints: [],
  carMarkersMap: new Map(),
  gpsWatchId: null,
  closestCar: null,
  activeDestinationCar: null
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

  // السحب والإفلات لملفات الإحالة المتعددة
  setupMultiDropzone("referralDropzone", "referralFileInput", (files) => {
    handleReferralFilesSelected(files);
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

// تنفيذ رفع ملف بيانات السيارات مع الضغط الفائق وتسريع النقل 8x ومؤشر رفع حي
async function uploadDatasetFile() {
  const fileInput = document.getElementById("datasetFileInput");
  const file = state.selectedDatasetFile || (fileInput ? fileInput.files[0] : null);
  if (!file) {
    showToast("يرجى اختيار ملف البيانات أولاً", "error");
    return;
  }

  const btn = document.getElementById("uploadDatasetBtn");
  const progressBar = document.getElementById("datasetProgressBar");
  const progressFill = document.getElementById("datasetProgressFill");
  const statusMsg = document.getElementById("datasetUploadMsg");

  btn.disabled = true;
  progressBar.style.display = "block";
  progressFill.style.width = "5%";

  let uploadFile = file;

  // 1. تقنية الضغط المحلي التلقائي الفائق (Client-Side Compression)
  // عند الرفع عبر الإنترنت (Codespaces أو خادم سحابي) يتم الضغط لتقليل الحجم بنسبة 85% وتسريع النقل
  // أما على الجهاز المحلي (localhost / 127.0.0.1) يتم الرفع المباشر فورياً بدون إضاعة وقت في المعالج
  const isLocalHost = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
  const isPlainCsv = file.name.toLowerCase().endsWith('.csv') || file.name.toLowerCase().endsWith('.txt') || file.name.toLowerCase().endsWith('.tsv');
  if (!isLocalHost && isPlainCsv && file.size > 2 * 1024 * 1024 && typeof CompressionStream !== 'undefined') {
    try {
      btn.innerText = "جاري الضغط الفائق...";
      statusMsg.innerText = "⚡ جاري ضغط الملف محلياً لتقليل حجمه 85% وتسريع النقل عبر الإنترنت...";
      progressFill.style.width = "20%";

      const cs = new CompressionStream('gzip');
      const stream = file.stream().pipeThrough(cs);
      const compressedBlob = await new Response(stream).blob();
      uploadFile = new File([compressedBlob], file.name + '.gz', { type: 'application/gzip' });

      const origMB = (file.size / (1024 * 1024)).toFixed(1);
      const newMB = (uploadFile.size / (1024 * 1024)).toFixed(1);
      statusMsg.innerText = `🚀 تم ضغط الحجم بنجاح من ${origMB}MB إلى ${newMB}MB! جاري الرفع الآن...`;
      progressFill.style.width = "30%";
    } catch (e) {
      console.warn("تخطي الضغط التلقائي والرفع المباشر:", e);
      uploadFile = file;
    }
  }

  btn.innerText = "جاري الرفع الآن...";
  const formData = new FormData();
  formData.append("file", uploadFile);

  // 2. استخدام XMLHttpRequest لتتبع نسبة الرفع المئوية الحية بدقة (Upload Progress)
  const xhr = new XMLHttpRequest();
  xhr.open("POST", "/api/dataset/upload", true);
  xhr.setRequestHeader("Authorization", `Bearer ${state.token}`);

  xhr.upload.onprogress = function (e) {
    if (e.lengthComputable) {
      const pct = Math.round((e.loaded / e.total) * 100);
      progressFill.style.width = Math.min(pct, 95) + "%";
      const loadedMB = (e.loaded / (1024 * 1024)).toFixed(1);
      const totalMB = (e.total / (1024 * 1024)).toFixed(1);
      if (pct < 100) {
        statusMsg.innerText = `جاري نقل البيانات: ${loadedMB}MB من أصل ${totalMB}MB (${pct}%)...`;
      } else {
        statusMsg.innerText = "⚡ تم الرفع بنجاح! جاري المعالجة وبناء الفهارس في محرك DuckDB C++ السريع...";
      }
    }
  };

  xhr.onload = async function () {
    progressFill.style.width = "100%";
    if (xhr.status >= 200 && xhr.status < 300) {
      try {
        const data = JSON.parse(xhr.responseText);
        showToast(data.message || "تم استبدال البيانات بنجاح في ثوانٍ معدودة!", "success");
        await loadDatasetStats();
        setTimeout(() => {
          closeUploadModal();
          btn.disabled = false;
          btn.innerText = "بدء رفع واستبدال البيانات";
        }, 1200);
      } catch (e) {
        showToast("تم الرفع بنجاح", "success");
        closeUploadModal();
      }
    } else {
      let errMsg = "فشل رفع الملف";
      try {
        const errData = JSON.parse(xhr.responseText);
        if (errData.detail) errMsg = errData.detail;
      } catch (e) {}
      showToast(errMsg, "error");
      btn.disabled = false;
      btn.innerText = "إعادة المحاولة";
      statusMsg.innerText = "⚠️ فشل الرفع. يرجى التأكد من صحة الملف وإعادة المحاولة.";
    }
  };

  xhr.onerror = function () {
    showToast("حدث خطأ في الاتصال أثناء الرفع", "error");
    btn.disabled = false;
    btn.innerText = "إعادة المحاولة";
    statusMsg.innerText = "⚠️ حدث خطأ في الشبكة.";
  };

  xhr.send(formData);
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

// رفع ملف أو ملفات الإحالة والبدء في المطابقة الفورية
async function uploadAndMatchReferral() {
  const files = state.selectedReferralFiles;
  if (!files || files.length === 0) {
    showToast("يرجى اختيار ملف إحالة واحد على الأقل", "error");
    return;
  }

  if (!state.datasetStats || state.datasetStats.total_records === 0) {
    showToast("تنبيه: قاعدة بيانات السيارات فارغة! يرجى رفع ملف السيارات أولاً.", "warning");
  }

  const formData = new FormData();
  files.forEach(f => {
    formData.append("files", f);
  });

  const btn = document.getElementById("startMatchBtn");
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner"></span> جاري المطابقة الفورية لـ ${files.length} ملف(ات)...`;

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
      await loadMapPoints();
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

// رسم رؤوس الأعمدة النظيفة بدون كتابة إحالة أو داتا
function renderTableHeaders(columns) {
  const thead = document.getElementById("resultsTableHead");
  if (!thead) return;

  if (!columns || columns.length === 0) {
    thead.innerHTML = "";
    return;
  }

  const ths = columns.map(col => {
    let extraClass = "";
    let cleanTitle = String(col)
      .replace(/^\[(الإحالة|السيارة)\]\s*/, '')
      .replace(/\s*\((داتا|إحالة)\)/, '')
      .trim();

    if (cleanTitle === "حالة المطابقة") {
      extraClass = "th-status sticky-col";
    }
    return `<th class="${extraClass}">${cleanTitle}</th>`;
  }).join("");

  thead.innerHTML = `<tr><th style="width: 45px; text-align:center;">#</th>${ths}<th style="text-align:center; min-width: 90px;">الخريطة</th></tr>`;
}

// رسم صفوف جدول النتائج بكافة الأعمدة النظيفة
function renderTableRows(records, columns) {
  const tableBody = document.getElementById("resultsTableBody");
  if (!tableBody) return;

  // حفظ السجلات الأخيرة لإمكانية إعادة رسم الأزرار فور تحميل الخريطة
  state.lastRecords = records;

  if (!records || records.length === 0) {
    const colCount = (columns ? columns.length : 10) + 2;
    tableBody.innerHTML = `<tr><td colspan="${colCount}" style="text-align:center; padding: 32px; color: var(--text-muted);">لا توجد سجلات مطابقة لهذا البحث أو الفلتر.</td></tr>`;
    return;
  }

  tableBody.innerHTML = records.map((r, idx) => {
    const rowNum = (state.currentPage - 1) * state.pageSize + idx + 1;

    // استخراج رقم اللوحة لهذا الصف للربط مع الخريطة
    const rowPlate = r['اللوحة'] || r['لوحة الإحالة'] || r['لوحة'] || '';
    const cleanPlateKey = String(rowPlate).trim();

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
          contentHtml = `<a href="${encodeURI(rawStr)}" target="_blank" rel="noopener noreferrer" class="map-link-btn" title="${rawStr}">📍 فتح الرابط</a>`;
        } else if ((col.includes('موقع') || col.includes('رابط') || col.includes('خريطة') || col.includes('location')) && rawStr.includes(',') && !isNaN(parseFloat(rawStr.split(',')[0]))) {
          contentHtml = `<a href="https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(rawStr)}" target="_blank" rel="noopener noreferrer" class="map-link-btn" title="${rawStr}">📍 فتح الإحداثيات</a>`;
        }
      }

      return `<td>${contentHtml}</td>`;
    }).join("");

    const safePlate = String(rowPlate).replace(/'/g, "\\'");
    const normPlate = cleanPlateKey.replace(/\s+/g, '');
    const refPlate = String(r['لوحة الإحالة'] || '').trim();
    const refPlateNorm = refPlate.replace(/\s+/g, '');
    const vehPlate = String(r['اللوحة'] || '').trim();
    const vehPlateNorm = vehPlate.replace(/\s+/g, '');

    // يظهر زر الخريطة إذا كانت السيارة تملك إحداثيات حقيقية مسجلة بأي صيغة
    const hasRealMapCoords = Boolean(
      state.carMarkersMap && (
        state.carMarkersMap.has(cleanPlateKey) ||
        state.carMarkersMap.has(normPlate) ||
        (refPlate && state.carMarkersMap.has(refPlate)) ||
        (refPlateNorm && state.carMarkersMap.has(refPlateNorm)) ||
        (vehPlate && state.carMarkersMap.has(vehPlate)) ||
        (vehPlateNorm && state.carMarkersMap.has(vehPlateNorm))
      )
    );
    let mapActionTd = "";
    if (hasRealMapCoords) {
      mapActionTd = `<td style="text-align:center;">
        <button class="btn-map-row" onclick="openMapModal('${safePlate}')" title="فتح الخريطة وتحديد موقع هذه السيارة وتوجيهك إليها">
          <span>📍</span> الخريطة
        </button>
      </td>`;
    } else {
      mapActionTd = `<td style="text-align:center;">
        <span class="no-loc-badge" title="لا تتوفر إحداثيات أو موقع حقيقي لهذه السيارة">لا يوجد موقع</span>
      </td>`;
    }

    return `<tr><td style="text-align:center; font-weight:700; color:#64748b;">${rowNum}</td>${tds}${mapActionTd}</tr>`;
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

// تصدير النتائج بأمان مع الحفاظ على رمز المصادقة والتحميل المباشر
async function triggerExport(format) {
  if (!state.token) {
    showToast("يرجى تسجيل الدخول أولاً لتصدير النتائج", "warning");
    return;
  }

  showToast(`جاري تجهيز وتحميل ملف الـ ${format.toUpperCase()} الشامل...`, "info");

  try {
    const query = new URLSearchParams({
      format: format,
      filter_status: state.currentFilter,
      token: state.token
    });

    const res = await fetch(`/api/referral/export?${query.toString()}`, {
      method: "GET",
      headers: {
        "Authorization": `Bearer ${state.token}`
      }
    });

    if (!res.ok) {
      let errorMsg = "فشل تحميل الملف";
      try {
        const err = await res.json();
        if (err && err.detail) errorMsg = err.detail;
      } catch (_) {}
      showToast(errorMsg, "error");
      return;
    }

    const blob = await res.blob();
    const blobUrl = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.style.display = "none";
    a.href = blobUrl;

    let filename = `نتائج_المطابقة_${state.currentFilter}_${new Date().toISOString().slice(0, 10)}.${format}`;
    const disposition = res.headers.get("Content-Disposition");
    if (disposition && disposition.includes("filename=")) {
      const match = disposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
      if (match && match[1]) {
        filename = decodeURIComponent(match[1].replace(/['"]/g, ""));
      }
    }

    a.download = filename;
    document.body.appendChild(a);
    a.click();

    setTimeout(() => {
      window.URL.revokeObjectURL(blobUrl);
      a.remove();
    }, 1000);

    showToast(`تم تحميل ملف الـ ${format.toUpperCase()} بنجاح ✅`, "success");
  } catch (err) {
    console.error("Export error:", err);
    showToast("حدث خطأ أثناء تحميل الملف، يرجى المحاولة لاحقاً", "error");
  }
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

// مساعد إعداد منطقة السحب والإفلات للملف الواحد
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

// مساعد إعداد منطقة السحب والإفلات لعدة ملفات إحالة معاً
function setupMultiDropzone(dropzoneId, inputId, onFilesSelect) {
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
      onFilesSelect(Array.from(e.dataTransfer.files));
    }
  });

  input.addEventListener("change", () => {
    if (input.files.length > 0) {
      onFilesSelect(Array.from(input.files));
      input.value = "";
    }
  });
}

// معالجة إضافة ملفات إحالة متعددة
function handleReferralFilesSelected(files) {
  if (!files || files.length === 0) return;

  for (let i = 0; i < files.length; i++) {
    const f = files[i];
    const exists = state.selectedReferralFiles.some(item => item.name === f.name && item.size === f.size);
    if (!exists) {
      state.selectedReferralFiles.push(f);
    }
  }

  renderSelectedReferralFiles();
}

// عرض قائمة الملفات المختارة مع إمكانية حذف أي ملف
function renderSelectedReferralFiles() {
  const container = document.getElementById("referralFilesList");
  const startBtn = document.getElementById("startMatchBtn");
  if (!container) return;

  if (state.selectedReferralFiles.length === 0) {
    container.innerHTML = "";
    if (startBtn) startBtn.disabled = true;
    return;
  }

  container.innerHTML = state.selectedReferralFiles.map((f, idx) => {
    const sizeMb = (f.size / (1024 * 1024)).toFixed(2);
    const sizeStr = f.size < 1024 * 1024 ? `${Math.round(f.size / 1024)} KB` : `${sizeMb} MB`;
    return `
      <div class="selected-file-chip">
        <span>📄 ${f.name} (${sizeStr})</span>
        <span class="remove-chip-btn" onclick="removeReferralFile(${idx})" title="إزالة هذا الملف">✕</span>
      </div>
    `;
  }).join("");

  if (startBtn) startBtn.disabled = false;
}

// إزالة ملف من قائمة ملفات الإحالة المختارة
function removeReferralFile(index) {
  state.selectedReferralFiles.splice(index, 1);
  renderSelectedReferralFiles();
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

// ==============================================================================
// محرك الخريطة التفاعلية وتتبع أسطول السيارات المتطابقة والملاحة (Fleet Map Engine)
// ==============================================================================

// تهيئة خريطة Leaflet
function initFleetMap() {
  if (typeof L === 'undefined') {
    console.warn("مكتبة Leaflet غير محملة بعد.");
    return false;
  }

  const mapContainer = document.getElementById("fleetMap");
  if (!mapContainer) return false;

  if (state.fleetMap) {
    state.fleetMap.invalidateSize();
    return true;
  }

  // إنشاء الخريطة مع مركز افتراضي (منطقة الرياض والمملكة)
  state.fleetMap = L.map('fleetMap', {
    zoomControl: true,
    scrollWheelZoom: true
  }).setView([24.7136, 46.6753], 11);

  // طبقة خرائط OpenStreetMap السريعة والمجانية
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '© OpenStreetMap contributors'
  }).addTo(state.fleetMap);

  // طبقة مخصصة لتجميع علامات السيارات
  state.markersLayer = L.layerGroup().addTo(state.fleetMap);

  return true;
}

// فتح نافذة الخريطة المنبثقة والتركيز على سيارة معينة أو كامل الأسطول
function openMapModal(plateToFocus = null) {
  const modal = document.getElementById("fleetMapModal");
  if (!modal) return;

  modal.classList.add("open");
  initFleetMap();

  setTimeout(() => {
    if (state.fleetMap) {
      state.fleetMap.invalidateSize();
      if (plateToFocus) {
        focusCarOnMap(plateToFocus);
      } else {
        fitAllCarsOnMap();
      }
    }
  }, 200);
}

// إغلاق نافذة الخريطة المنبثقة
function closeMapModal() {
  const modal = document.getElementById("fleetMapModal");
  if (modal) {
    modal.classList.remove("open");
  }
}

// تحميل نقاط السيارات المتطابقة من السيرفر ورسمها على الخريطة
async function loadMapPoints() {
  initFleetMap();

  const countBadge = document.getElementById("mapCarCount");
  const toolbarCount = document.getElementById("toolbarMapCount");

  try {
    const res = await fetch("/api/referral/map-points", {
      headers: { "Authorization": `Bearer ${state.token}` }
    });

    const data = await res.json();
    const points = (data.success && data.points) ? data.points : [];

    state.mapPoints = points;
    if (countBadge) countBadge.innerText = `${points.length} موقع`;
    if (toolbarCount) toolbarCount.innerText = `${points.length}`;

    // تنظيف العلامات السابقة
    if (state.markersLayer) {
      state.markersLayer.clearLayers();
    }
    state.carMarkersMap.clear();

    const boundsList = [];

    points.forEach(p => {
      if (typeof p.lat !== 'number' || typeof p.lng !== 'number') return;

      const isMulti = (p.status === 'تطابق متعدد');
      const safePlate = (p.plate || '').replace(/"/g, '&quot;');
      const plateKey = String(p.plate || '').trim();

      // أيقونة مخصصة لكل سيارة
      const iconHtml = `<div class="car-marker-icon ${isMulti ? 'multi' : ''}" title="لوحة: ${safePlate}">🚗 ${safePlate}</div>`;
      const customIcon = L.divIcon({
        className: 'custom-car-pin-wrap',
        html: iconHtml,
        iconSize: [85, 26],
        iconAnchor: [42, 13]
      });

      const marker = L.marker([p.lat, p.lng], { icon: customIcon });

      // محتوى النافذة المنبثقة للسيارة
      const popupHtml = `
        <div class="map-car-popup">
          <div class="map-car-popup-header">
            <span class="map-car-popup-plate">🚗 ${safePlate}</span>
            <span class="badge ${isMulti ? 'badge-multiple' : 'badge-matched'}">${p.status}</span>
          </div>
          <div class="map-car-popup-info">
            ${p.type ? `<div><strong>النوع:</strong> ${p.type}</div>` : ''}
            ${p.client ? `<div><strong>العميل:</strong> ${p.client}</div>` : ''}
            ${p.street ? `<div><strong>الشارع:</strong> ${p.street}</div>` : ''}
            ${p.district ? `<div><strong>الحي:</strong> ${p.district}</div>` : ''}
            ${p.date ? `<div><strong>التاريخ:</strong> ${p.date}</div>` : ''}
            <div id="popup-dist-${escapeId(plateKey)}" class="map-car-popup-dist" style="display:none;"></div>
          </div>
          <div class="map-car-popup-actions">
            <button class="btn btn-primary btn-sm" onclick="drawRouteToCar(${p.lat}, ${p.lng}, '${plateKey.replace(/'/g, "\\'")}')">
              🚗 مسار السير
            </button>
            <a href="https://www.google.com/maps/dir/?api=1&destination=${p.lat},${p.lng}&travelmode=driving" target="_blank" rel="noopener noreferrer" class="btn btn-secondary btn-sm">
              🧭 خرائط Google
            </a>
          </div>
        </div>
      `;

      marker.bindPopup(popupHtml);

      // حفظ العلامة في الخريطة والقاموس بمختلف صيغ اللوحات لضمان التطابق التام
      marker.addTo(state.markersLayer);
      state.carMarkersMap.set(plateKey, marker);
      state.carMarkersMap.set(plateKey.replace(/\s+/g, ''), marker);
      if (p.ref_plate) {
        const refKey = String(p.ref_plate).trim();
        state.carMarkersMap.set(refKey, marker);
        state.carMarkersMap.set(refKey.replace(/\s+/g, ''), marker);
      }
      boundsList.push([p.lat, p.lng]);
    });

    // احتواء كافة السيارات داخل إطار العرض إذا كانت الخريطة مفتوحة
    if (boundsList.length > 0 && state.fleetMap) {
      if (state.userLocation) {
        boundsList.push([state.userLocation.lat, state.userLocation.lng]);
      }
      state.fleetMap.fitBounds(boundsList, { padding: [40, 40], maxZoom: 15 });
    }

    // تحديث مسافات السيارات وأقرب سيارة إذا كان موقع المستخدم متاحًا
    if (state.userLocation) {
      updateDistancesAndClosestCar();
    }

    // إعادة رسم صفوف الجدول لتفعيل أزرار الخريطة للسيارات التي لها إحداثيات حقيقية فقط
    if (state.lastRecords && state.columns) {
      renderTableRows(state.lastRecords, state.columns);
    }

    setTimeout(() => {
      if (state.fleetMap) state.fleetMap.invalidateSize();
    }, 250);

  } catch (err) {
    console.error("فشل جلب نقاط خريطة السيارات:", err);
  }
}

// إظهار كافة السيارات على الخريطة (مع حل مشكلة التعليق بعد التتبع)
function fitAllCarsOnMap() {
  if (!state.fleetMap) return;

  // فك قفل الهدف السابق ومسح المسار الأحادي
  state.activeDestinationCar = null;
  if (state.routePolyline) {
    state.fleetMap.removeLayer(state.routePolyline);
    state.routePolyline = null;
  }
  state.fleetMap.closePopup();

  if (state.carMarkersMap.size === 0) {
    if (state.userLocation) {
      state.fleetMap.setView([state.userLocation.lat, state.userLocation.lng], 13);
    }
    showToast("لا توجد سيارات بإحداثيات حقيقية لعرضها حالياً", "info");
    return;
  }

  // تجميع كافة علامات السيارات وموقع المستخدم
  const group = L.featureGroup(Array.from(state.carMarkersMap.values()));
  if (state.userGpsMarker) {
    group.addLayer(state.userGpsMarker);
  }

  state.fleetMap.fitBounds(group.getBounds(), { padding: [50, 50], maxZoom: 15 });
  showToast(`تم إظهار كافة السيارات على الخريطة (${state.carMarkersMap.size} سيارة)`, "info");
}

// تفعيل / إيقاف تتبع موقع المستخدم بالـ GPS الحي
function toggleGpsTracking() {
  if (state.gpsWatchId !== null) {
    // إيقاف التتبع
    navigator.geolocation.clearWatch(state.gpsWatchId);
    state.gpsWatchId = null;

    const iconEl = document.getElementById("gpsBtnIcon");
    const textEl = document.getElementById("gpsBtnText");
    if (iconEl) iconEl.innerText = "📡";
    if (textEl) textEl.innerText = "تتبع موقعي وتحديد أقرب سيارة";

    showToast("تم إيقاف تتبع الموقع", "info");
    return;
  }

  if (!navigator.geolocation) {
    showToast("خاصية تحديد الموقع الجغرافي (GPS) غير مدعومة في هذا المتصفح", "error");
    return;
  }

  const iconEl = document.getElementById("gpsBtnIcon");
  const textEl = document.getElementById("gpsBtnText");
  if (iconEl) iconEl.innerText = "⏳";
  if (textEl) textEl.innerText = "جاري الاتصال بالـ GPS...";

  state.gpsWatchId = navigator.geolocation.watchPosition(
    onGpsSuccess,
    onGpsError,
    {
      enableHighAccuracy: true,
      timeout: 12000,
      maximumAge: 1000
    }
  );
}

// عند استلام إحداثيات GPS المستخدم بنجاح
function onGpsSuccess(pos) {
  const { latitude, longitude, accuracy } = pos.coords;
  state.userLocation = { lat: latitude, lng: longitude, accuracy };

  const iconEl = document.getElementById("gpsBtnIcon");
  const textEl = document.getElementById("gpsBtnText");
  if (iconEl) iconEl.innerText = "🟢";
  if (textEl) textEl.innerText = "جاري تتبع موقعك المباشر (نشط)";

  // رسم أو تحريك علامة المستخدم على الخريطة
  const userIcon = L.divIcon({
    className: 'user-gps-marker',
    html: `
      <div class="user-gps-pulse-wrap" title="موقعك الحالي (دقة: ${Math.round(accuracy)} م)">
        <div class="user-gps-ring"></div>
        <div class="user-gps-dot"></div>
      </div>
    `,
    iconSize: [32, 32],
    iconAnchor: [16, 16]
  });

  if (!state.userGpsMarker) {
    state.userGpsMarker = L.marker([latitude, longitude], {
      icon: userIcon,
      zIndexOffset: 1000
    }).addTo(state.fleetMap);
  } else {
    state.userGpsMarker.setLatLng([latitude, longitude]);
  }

  // تحديث المسافات واختيار أقرب سيارة
  updateDistancesAndClosestCar();

  // تحديث مسار السير المرسوم إذا كان هناك سيارة هدف نشطة
  if (state.activeDestinationCar) {
    drawRouteToCar(state.activeDestinationCar.lat, state.activeDestinationCar.lng, state.activeDestinationCar.plate, false);
  }
}

// عند حدوث خطأ في GPS
function onGpsError(err) {
  console.warn("GPS Error:", err);
  const iconEl = document.getElementById("gpsBtnIcon");
  const textEl = document.getElementById("gpsBtnText");
  if (iconEl) iconEl.innerText = "📡";
  if (textEl) textEl.innerText = "تتبع موقعي وتحديد أقرب سيارة";
  state.gpsWatchId = null;

  let msg = "تعذر تحديد موقعك الحالي.";
  if (err.code === 1) msg = "تم رفض إذن الوصول إلى الموقع الجغرافي من المتصفح.";
  else if (err.code === 2) msg = "إشارة GPS غير متوفرة حالياً.";
  else if (err.code === 3) msg = "انتهت مهلة استجابة الـ GPS.";
  showToast(msg, "warning");
}

// حساب المسافات لجميع السيارات واختيار أقرب سيارة لموقع المستخدم
function updateDistancesAndClosestCar() {
  if (!state.userLocation || !state.mapPoints || state.mapPoints.length === 0) return;

  const uLat = state.userLocation.lat;
  const uLng = state.userLocation.lng;

  const pointsWithDist = state.mapPoints.map(p => {
    const dist = calculateDistanceMeters(uLat, uLng, p.lat, p.lng);
    return { ...p, distanceMeters: dist };
  });

  // ترتيب تصاعدي حسب المسافة
  pointsWithDist.sort((a, b) => a.distanceMeters - b.distanceMeters);

  const closest = pointsWithDist[0];
  state.closestCar = closest;

  // تحديث شريط تنبيه أقرب سيارة
  const banner = document.getElementById("closestCarAlert");
  const detailsEl = document.getElementById("closestCarDetails");
  const routeBtn = document.getElementById("btnRouteToClosest");
  const navBtn = document.getElementById("btnNavGoogleMaps");

  if (banner && detailsEl && closest) {
    const distText = formatDistance(closest.distanceMeters);
    detailsEl.innerHTML = `
      اللوحة: <strong style="color:#0f172a; font-size:15px;">${closest.plate}</strong>
      ${closest.model ? `• الطراز: ${closest.model}` : ''}
      ${closest.notes ? `• ${closest.notes}` : ''}
      — <span style="background:#dcfce7; color:#15803d; padding:2px 8px; border-radius:6px; font-weight:800;">📏 المسافة: ${distText}</span>
    `;

    banner.style.display = "flex";

    if (routeBtn) {
      routeBtn.onclick = () => {
        focusCarOnMap(closest.plate);
        drawRouteToCar(closest.lat, closest.lng, closest.plate);
      };
    }

    if (navBtn) {
      navBtn.href = `https://www.google.com/maps/dir/?api=1&origin=${uLat},${uLng}&destination=${closest.lat},${closest.lng}&travelmode=driving`;
    }
  }

  // تحديث المسافة داخل نوافذ الـ Popup المفتوحة
  pointsWithDist.forEach(p => {
    const el = document.getElementById(`popup-dist-${escapeId(p.plate)}`);
    if (el) {
      el.style.display = "inline-flex";
      el.innerText = `📏 على بعد: ${formatDistance(p.distanceMeters)}`;
    }
  });
}

// رسم مسار السير والتوجيه من موقع المستخدم إلى سيارة محددة
function drawRouteToCar(carLat, carLng, plate, doToast = true) {
  if (!state.fleetMap) return;

  state.activeDestinationCar = { lat: carLat, lng: carLng, plate };

  if (!state.userLocation) {
    // تشغيل الـ GPS إذا لم يكن مفعلاً
    toggleGpsTracking();
    showToast("جاري تحديد موقعك لرسم خط التوجيه نحو السيارة...", "info");
    return;
  }

  const uLat = state.userLocation.lat;
  const uLng = state.userLocation.lng;

  // مسح أي مسار سابق
  if (state.routePolyline) {
    state.fleetMap.removeLayer(state.routePolyline);
  }

  // رسم خط المسار المتقطع الأنيق
  state.routePolyline = L.polyline([
    [uLat, uLng],
    [carLat, carLng]
  ], {
    color: '#2563eb',
    weight: 4,
    opacity: 0.85,
    dashArray: '8, 8',
    lineCap: 'round'
  }).addTo(state.fleetMap);

  // احتواء المسار في الشاشة
  state.fleetMap.fitBounds([
    [uLat, uLng],
    [carLat, carLng]
  ], { padding: [70, 70] });

  const dist = calculateDistanceMeters(uLat, uLng, carLat, carLng);
  if (doToast) {
    showToast(`تم رسم مسار التوجيه نحو السيارة (${plate}) • المسافة: ${formatDistance(dist)}`, "success");
  }
}

// تركيز الخريطة على سيارة محددة باللوحة (من الجدول أو البحث)
function focusCarOnMap(plate) {
  if (!initFleetMap()) return;

  const cleanPlate = String(plate).trim();
  const normPlate = cleanPlate.replace(/\s+/g, '');
  const marker = state.carMarkersMap.get(cleanPlate) || state.carMarkersMap.get(normPlate);

  // فتح نافذة الخريطة المنبثقة أولاً
  const modal = document.getElementById("fleetMapModal");
  if (modal && !modal.classList.contains("open")) {
    modal.classList.add("open");
  }

  setTimeout(() => {
    if (state.fleetMap) {
      state.fleetMap.invalidateSize();
    }

    if (marker) {
      const latLng = marker.getLatLng();
      state.fleetMap.setView(latLng, 16, { animate: true });
      setTimeout(() => {
        marker.openPopup();
        if (state.userLocation) {
          drawRouteToCar(latLng.lat, latLng.lng, cleanPlate, true);
        }
      }, 350);
    } else {
      showToast(`لا تتوفر إحداثيات موقع مسجلة للوحة: ${cleanPlate}`, "info");
    }
  }, 200);
}

// معادلة Haversine لحساب المسافة بدقة بالمتر بين إحداثيتين
function calculateDistanceMeters(lat1, lon1, lat2, lon2) {
  const R = 6371000; // نصف قطر الأرض بالأمتار
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLon = (lon2 - lon1) * Math.PI / 180;
  const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
            Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
            Math.sin(dLon / 2) * Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
}

// تنسيق المسافة بالمتر أو الكيلومتر
function formatDistance(meters) {
  if (isNaN(meters) || meters === null) return "-";
  if (meters < 1000) {
    return `${Math.round(meters)} متر`;
  }
  return `${(meters / 1000).toFixed(1)} كم`;
}

// تنظيف المعرفات لاستخدامها في الـ DOM
function escapeId(str) {
  return String(str).replace(/[^a-zA-Z0-9_\u0600-\u06FF]/g, '_');
}

