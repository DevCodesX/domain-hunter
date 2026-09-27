document.addEventListener('DOMContentLoaded', () => {
    // State
    let currentPage = 1;
    let totalItems = 0;
    let selectedIds = new Set();
    let currentData = [];
    let searchTimeout = null;

    // Elements
    const searchInput = document.getElementById('search-input');
    const dateFilter = document.getElementById('date-filter');
    const categoryFilter = document.getElementById('category-filter');
    const sortFilter = document.getElementById('sort-filter');
    const limitFilter = document.getElementById('limit-filter');
    
    const tableBody = document.getElementById('table-body');
    const paginationInfo = document.getElementById('pagination-info');
    const pageIndicator = document.getElementById('page-indicator');
    const btnPrev = document.getElementById('btn-prev');
    const btnNext = document.getElementById('btn-next');
    
    const selectAllPage = document.getElementById('select-all-page');
    const selectionCount = document.getElementById('selection-count');
    const clearSelectionBtn = document.getElementById('clear-selection');
    
    const exportDropdownBtn = document.getElementById('export-dropdown-btn');
    const exportMenu = document.getElementById('export-menu');
    const loadingOverlay = document.getElementById('loading-overlay');
    const loadingText = document.getElementById('loading-text');
    const toast = document.getElementById('toast');

    // Modal
    const modal = document.getElementById('detail-modal');
    const modalClose = document.getElementById('modal-close');
    const modalDomain = document.getElementById('modal-domain');
    const modalCategory = document.getElementById('modal-category');
    const modalDate = document.getElementById('modal-date');
    const modalGodaddy = document.getElementById('modal-godaddy-link');

    function showToast(msg) {
        toast.innerText = msg;
        toast.classList.remove('hidden');
        setTimeout(() => toast.classList.add('hidden'), 3000);
    }

    // Toggle dropdown
    exportDropdownBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        exportMenu.classList.toggle('show');
    });

    window.addEventListener('click', () => {
        if(exportMenu.classList.contains('show')) exportMenu.classList.remove('show');
    });

    // Date Helper
    function getFromDate(value) {
        if(!value) return null;
        const now = new Date();
        if(value === '24h') now.setHours(now.getHours() - 24);
        else if(value === '3d') now.setDate(now.getDate() - 3);
        else if(value === '7d') now.setDate(now.getDate() - 7);
        else if(value === '30d') now.setDate(now.getDate() - 30);
        else if(value === '90d') now.setDate(now.getDate() - 90);
        return now.toISOString();
    }

    async function loadStats() {
        try {
            const res = await fetch('/api/domains/history/stats');
            const data = await res.json();
            if(data.success && data.stats) {
                const cards = document.querySelectorAll('.stat-card h3');
                cards[0].innerText = data.stats.last_24h.toLocaleString();
                cards[1].innerText = data.stats.last_7d.toLocaleString();
                cards[2].innerText = data.stats.last_30d.toLocaleString();
                cards[3].innerText = data.stats.total.toLocaleString();
            }
        } catch(e) {
            console.error('Stats error:', e);
        }
    }

    async function loadData() {
        tableBody.innerHTML = '<tr><td colspan="4" style="text-align:center;"><i class="fa-solid fa-spinner fa-spin"></i> جاري التحميل...</td></tr>';
        
        const params = new URLSearchParams();
        params.append('page', currentPage);
        params.append('limit', limitFilter.value);
        params.append('sort', sortFilter.value);
        
        if (searchInput.value.trim()) params.append('search', searchInput.value.trim());
        if (categoryFilter.value) params.append('category', categoryFilter.value);
        
        const fromDate = getFromDate(dateFilter.value);
        if (fromDate) params.append('from_date', fromDate);

        try {
            const res = await fetch(`/api/domains/history?${params.toString()}`);
            const data = await res.json();
            
            if(data.error) {
                throw new Error(data.error);
            }
            
            currentData = data.data || [];
            totalItems = data.total || 0;
            
            renderTable();
            updatePagination();
            updateSelectionUI();
        } catch(e) {
            tableBody.innerHTML = `<tr><td colspan="4" style="text-align:center; color:#ef4444;">تعذر تحميل البيانات: ${e.message}</td></tr>`;
        }
    }

    function renderTable() {
        if(currentData.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="4" style="text-align:center; color:#94a3b8;">لا توجد نتائج مطابقة للبحث.</td></tr>';
            return;
        }

        let html = '';
        currentData.forEach(d => {
            const isChecked = selectedIds.has(d.id) ? 'checked' : '';
            const dDate = new Date(d.created_at).toLocaleString('ar-EG');
            
            html += `
                <tr style="cursor:pointer;" data-id="${d.id}" class="domain-row">
                    <td onclick="event.stopPropagation()"><input type="checkbox" class="row-checkbox" value="${d.id}" ${isChecked}></td>
                    <td style="font-family: monospace; font-size:1.1rem; color:#f8fafc; direction:ltr; text-align:right;">${d.domain_name}</td>
                    <td><span class="badge" style="background:rgba(59,130,246,0.2); color:#3b82f6;">${d.category || 'عام'}</span></td>
                    <td style="font-size:0.9rem; color:#94a3b8; direction:ltr; text-align:right;">${dDate}</td>
                </tr>
            `;
        });
        tableBody.innerHTML = html;

        // Row clicks for modal
        document.querySelectorAll('.domain-row').forEach(row => {
            row.addEventListener('click', () => {
                const id = parseInt(row.getAttribute('data-id'));
                const domain = currentData.find(x => x.id === id);
                if(domain) openModal(domain);
            });
        });

        // Checkbox events
        document.querySelectorAll('.row-checkbox').forEach(cb => {
            cb.addEventListener('change', (e) => {
                const id = parseInt(e.target.value);
                if(e.target.checked) selectedIds.add(id);
                else selectedIds.delete(id);
                updateSelectionUI();
            });
        });
        
        checkSelectAllState();
    }

    function updatePagination() {
        const limit = parseInt(limitFilter.value);
        const totalPages = Math.ceil(totalItems / limit) || 1;
        
        pageIndicator.innerText = `صفحة ${currentPage} من ${totalPages}`;
        
        const start = ((currentPage - 1) * limit) + 1;
        const end = Math.min(currentPage * limit, totalItems);
        paginationInfo.innerText = totalItems > 0 ? `عرض ${start}-${end} من إجمالي ${totalItems} نطاق` : '';

        btnPrev.disabled = currentPage <= 1;
        btnNext.disabled = currentPage >= totalPages;
    }

    function updateSelectionUI() {
        selectionCount.innerText = `${selectedIds.size} محدد`;
        clearSelectionBtn.style.display = selectedIds.size > 0 ? 'inline-block' : 'none';
        checkSelectAllState();
    }

    function checkSelectAllState() {
        if(currentData.length === 0) {
            selectAllPage.checked = false;
            return;
        }
        const allOnPageSelected = currentData.every(d => selectedIds.has(d.id));
        selectAllPage.checked = allOnPageSelected;
    }

    // Export Handler globally accessible
    window.exportData = async function(selectionType, format) {
        if(selectionType === 'selected' && selectedIds.size === 0) {
            showToast('الرجاء تحديد نطاقات أولاً');
            return;
        }

        loadingText.innerText = 'جاري تحضير التصدير...';
        loadingOverlay.style.display = 'flex';

        const payload = {
            format: format,
            selection: selectionType,
            selected_ids: Array.from(selectedIds),
            search: searchInput.value.trim() || null,
            category: categoryFilter.value || null,
            sort: sortFilter.value,
            from_date: getFromDate(dateFilter.value)
        };

        try {
            const response = await fetch('/api/domains/export', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (!response.ok) throw new Error('Export failed');

            if (format === 'json') {
                const json = await response.json();
                const blob = new Blob([JSON.stringify(json, null, 2)], { type: 'application/json' });
                downloadBlob(blob, 'export.json');
            } else {
                const blob = await response.blob();
                let filename = 'export.' + format;
                const disposition = response.headers.get('Content-Disposition');
                if (disposition && disposition.indexOf('filename=') !== -1) {
                    filename = disposition.split('filename=')[1].replace(/"/g, '');
                }
                downloadBlob(blob, filename);
            }
            showToast('تم التصدير بنجاح');
        } catch (e) {
            showToast('حدث خطأ أثناء التصدير');
            console.error(e);
        } finally {
            loadingOverlay.style.display = 'none';
        }
    };

    function downloadBlob(blob, filename) {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
    }

    // Modal logic
    function openModal(domain) {
        modalDomain.innerText = domain.domain_name;
        modalCategory.innerText = domain.category || 'عام';
        const modalScore = document.getElementById('modal-score');
        const scoreVal = (domain.overall_score !== undefined && domain.overall_score !== null) ? domain.overall_score : 'N/A';
        if (modalScore) modalScore.innerText = `النقاط: ${scoreVal}`;
        const modalProvider = document.getElementById('modal-provider');
        const rawProv = (domain.availability_provider || '').trim();
        const isMock = rawProv.toLowerCase().includes('mock');
        let provLabel = isMock ? '🧪 TEST — mock provider' : `✓ VERIFIED — ${(rawProv === 'verisign_rdap' || !rawProv) ? 'Verisign RDAP' : rawProv}`;
        if (modalProvider) modalProvider.innerText = provLabel;
        modalDate.innerText = new Date(domain.checked_at || domain.created_at).toLocaleString('ar-EG');
        modalGodaddy.href = `https://www.godaddy.com/domainsearch/find?checkAvail=1&domainToCheck=${domain.domain_name}`;
        modal.classList.add('active');
    }

    modalClose.addEventListener('click', () => {
        modal.classList.remove('active');
    });

    // Event Listeners
    searchInput.addEventListener('input', () => {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(() => {
            currentPage = 1;
            loadData();
        }, 500);
    });

    [dateFilter, categoryFilter, sortFilter, limitFilter].forEach(el => {
        el.addEventListener('change', () => {
            currentPage = 1;
            loadData();
        });
    });

    btnPrev.addEventListener('click', () => {
        if(currentPage > 1) {
            currentPage--;
            loadData();
        }
    });

    btnNext.addEventListener('click', () => {
        currentPage++;
        loadData();
    });

    selectAllPage.addEventListener('change', (e) => {
        const checked = e.target.checked;
        currentData.forEach(d => {
            if(checked) selectedIds.add(d.id);
            else selectedIds.delete(d.id);
        });
        updateSelectionUI();
        renderTable(); // Update row checkboxes
    });

    clearSelectionBtn.addEventListener('click', () => {
        selectedIds.clear();
        updateSelectionUI();
        renderTable();
    });

    // Init
    loadStats();
    loadData();
});
