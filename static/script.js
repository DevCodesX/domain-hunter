document.addEventListener('DOMContentLoaded', () => {
    // Elements
    const btnRefresh = document.getElementById('btn-refresh');
    const timeDisplay = document.getElementById('time-display');
    const toast = document.getElementById('toast');
    const mainGrid = document.getElementById('main-grid');

    const tier1Countries = [
        { code: 'US', name: 'الولايات المتحدة', lang: 'en', flag: '🇺🇸', color: '#3b82f6' },
        { code: 'GB', name: 'المملكة المتحدة', lang: 'en', flag: '🇬🇧', color: '#ef4444' },
        { code: 'CA', name: 'كندا', lang: 'en', flag: '🇨🇦', color: '#ef4444' },
        { code: 'AU', name: 'أستراليا', lang: 'en', flag: '🇦🇺', color: '#10b981' }
    ];

    const skeletonHTML = `
        <div class="skeleton-loader"></div>
        <div class="skeleton-loader"></div>
        <div class="skeleton-loader"></div>
    `;

    let refreshInterval;
    let aiRefreshInterval;
    let isAILoading = false;

    function showToast() {
        toast.classList.remove('hidden');
        setTimeout(() => toast.classList.add('hidden'), 3000);
    }

    function updateTime() {
        const now = new Date();
        timeDisplay.innerText = now.toLocaleTimeString('ar-EG');
    }

    // Initialize layout
    function initLayout() {
        mainGrid.innerHTML = '';
        tier1Countries.forEach(country => {
            const section = document.createElement('section');
            section.className = 'dashboard-category glass-panel';
            section.id = `section-${country.code}`;
            
            section.innerHTML = `
                <div class="category-header" style="border-bottom-color: ${country.color}55;">
                    <h2><span style="font-size:1.5rem;">${country.flag}</span> ${country.name}</h2>
                    <span class="badge" style="background: ${country.color}33; color: ${country.color}">مباشر</span>
                </div>
                <div class="category-content" id="content-${country.code}">
                    ${skeletonHTML}
                </div>
            `;
            mainGrid.appendChild(section);
        });
    }

    const globalCategory = document.getElementById('global-category');

    async function fetchCountryData(country) {
        const contentDiv = document.getElementById(`content-${country.code}`);
        const category = globalCategory.value;
        
        try {
            let html = '';
            let topKeyword = '';
            let trendsData = [];

            // 1. Fetch Trends (General RSS or Category News)
            if (category === 'ALL') {
                const resRss = await fetch(`/api/trends/rss?geo=${country.code}`);
                const dataRss = await resRss.json();
                if (!dataRss.error && dataRss.trends) {
                    trendsData = dataRss.trends;
                }
            } else {
                const resCat = await fetch(`/api/trends/category?geo=${country.code}&lang=${country.lang}&topic=${category}`);
                const dataCat = await resCat.json();
                if (!dataCat.error && dataCat.trends) {
                    trendsData = dataCat.trends;
                }
            }

            if (trendsData.length > 0) {
                const icon = category === 'ALL' ? 'fa-fire-flame-curved' : 'fa-layer-group';
                const label = category === 'ALL' ? 'التريند العام' : 'مواضيع رائجة في المجال';
                
                html += `<div class="section-title"><i class="fa-solid ${icon}" style="color: #ef4444;"></i> ${label}</div>`;
                
                // Show top 3
                const topTrends = trendsData.slice(0, 3);
                topTrends.forEach(trend => {
                    const trafficOrDate = trend.traffic ? 
                        `<div class="traffic"><i class="fa-solid fa-arrow-trend-up"></i> ${trend.traffic}</div>` : 
                        `<div style="font-size: 0.75rem; color: #94a3b8; margin-top: 0.3rem;"><i class="fa-regular fa-clock"></i> ${new Date(trend.pubDate || Date.now()).toLocaleTimeString('ar-EG')}</div>`;
                    
                    html += `
                        <div class="trend-card" style="padding: 1rem; margin-bottom: 0.8rem;">
                            <h4 style="font-size:0.95rem; margin-bottom: 0;">${trend.title || 'بدون عنوان'}</h4>
                            ${trafficOrDate}
                        </div>
                    `;
                });
                
                topKeyword = trendsData[0].title;
            }

            // 2. Fetch Google Suggest for the top keyword
            if (topKeyword) {
                try {
                    const resSuggest = await fetch(`/api/suggest?q=${encodeURIComponent(topKeyword)}&hl=${country.lang}&gl=${country.code.toLowerCase()}`);
                    const dataSuggest = await resSuggest.json();
                    
                    if (!dataSuggest.error && dataSuggest.suggestions && dataSuggest.suggestions.length > 0) {
                        html += `<div class="section-title" style="margin-top:1.5rem;"><i class="fa-brands fa-google" style="color: #3b82f6;"></i> مقترحات لكلمة: "${topKeyword}"</div>`;
                        html += `<div class="keyword-tags-container">`;
                        
                        // Limit to 5 suggestions
                        const suggestions = dataSuggest.suggestions.slice(0, 5);
                        suggestions.forEach(suggestion => {
                            const text = Array.isArray(suggestion) ? suggestion[0] : suggestion;
                            html += `<span class="keyword-tag" style="font-size:0.8rem; padding: 0.3rem 0.6rem;">${text}</span>`;
                        });
                        html += `</div>`;
                    }
                } catch (e) {
                    console.error("Suggest error for", country.code, e);
                }
            }

            contentDiv.innerHTML = html || '<p>لا توجد بيانات حالياً.</p>';

        } catch (error) {
            contentDiv.innerHTML = `<div class="error-message">خطأ في الجلب: ${error.message}</div>`;
        }
    }

    async function fetchAIDomains() {
        if (isAILoading) return;
        isAILoading = true;
        
        const aiContainer = document.getElementById('ai-domains-container');
        
        try {
            if (aiContainer.innerHTML.includes('fa-robot')) {
                aiContainer.innerHTML = skeletonHTML;
            }
            
            const res = await fetch(`/api/domains/latest`);
            if (res.status === 404) {
                aiContainer.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: #94a3b8; padding: 2rem;">
                    <i class="fa-solid fa-clock-rotate-left fa-2x" style="margin-bottom: 1rem;"></i>
                    <p>لا يوجد بحث يومي مكتمل بعد. يمكنك بدء فحص يدوي الآن.</p>
                </div>`;
                return;
            }
            
            const data = await res.json();
            if (data.error || data.success === false) {
                throw new Error(data.message || 'Unknown error');
            }
            
            let html = '';
            
            html += `<div style="grid-column: 1/-1; margin-bottom: 1rem; padding: 0.75rem 1rem; background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.25); color: #10b981; border-radius: 8px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem;">
                <div><i class="fa-solid fa-circle-check"></i> <strong>فرص مؤكدة الإتاحة الرسمية</strong> — جميع النطاقات مفحوصة ومتاحة للتسجيل العادي (Standard Registration) وليست محجوزة أو بريميوم.</div>
            </div>`;
            
            if (data.scan && data.scan.domains_found !== undefined) {
                const scanTime = data.scan.completed_at ? new Date(data.scan.completed_at).toLocaleString('ar-EG') : 'الآن';
                html += `<div style="grid-column: 1/-1; margin-bottom: 1.5rem; background: rgba(15, 23, 42, 0.5); border: 1px dashed rgba(16, 185, 129, 0.4); padding: 1rem; border-radius: 8px; display: flex; justify-content: space-around; text-align: center; flex-wrap: wrap; gap: 1rem;">
                    <div><span style="font-size:0.8rem; color:#94a3b8;">إجمالي الفرص المؤكدة:</span><br><b style="font-size:1.3rem; color:#10b981;">${data.scan.domains_found}</b></div>
                    <div><span style="font-size:0.8rem; color:#94a3b8;">حالة التحقق:</span><br><b style="font-size:1.1rem; color:#34d399;">✓ AVAILABLE_STANDARD</b></div>
                    <div><span style="font-size:0.8rem; color:#94a3b8;">تاريخ آخر فحص:</span><br><b style="font-size:0.95rem; color:#e2e8f0; direction:ltr; display:inline-block;">${scanTime}</b></div>
                </div>`;
            }
            
            if (data.concepts && data.concepts.length > 0) {
                 html += `
                    <div style="grid-column: 1/-1; margin-bottom: 1rem;">
                        <span style="font-size: 0.85rem; color: #94a3b8; display: block; margin-bottom: 0.5rem;"><i class="fa-solid fa-microscope"></i> استنتاجات البحث للتريندات العالمية:</span>
                        <div class="keyword-tags-container" style="display: flex; gap: 0.5rem; flex-wrap: wrap;">`;
                    data.concepts.forEach(concept => {
                        html += `<span class="keyword-tag" style="background: rgba(251, 191, 36, 0.1); border-color: rgba(251, 191, 36, 0.3); color: #fbbf24; font-size: 0.8rem; padding: 0.3rem 0.6rem; border-radius: 4px; border: 1px solid;">${concept}</span>`;
                    });
                    html += `</div></div>`;
            }

            html += `<div style="grid-column: 1/-1; display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 1.5rem;">`;
            if (data.domains && data.domains.length > 0) {
                data.domains.forEach(d => {
                    const dName = d.domain_name || d.domain;
                    const fScores = (d.quality_breakdown && d.quality_breakdown._float_scores) || {};
                    const overallRaw = (d.overall_score !== undefined && d.overall_score !== null) ? d.overall_score : ((d.quality_score !== undefined && d.quality_score !== null) ? d.quality_score : 0);
                    const overall = typeof overallRaw === 'number' ? (Number.isInteger(overallRaw) ? overallRaw : overallRaw.toFixed(1)) : overallRaw;
                    const brandRaw = (fScores.brandability !== undefined) ? fScores.brandability : ((d.brandability_score !== undefined && d.brandability_score !== null) ? d.brandability_score : (d.quality_breakdown && d.quality_breakdown.brandability !== undefined ? d.quality_breakdown.brandability : 0));
                    const brand = typeof brandRaw === 'number' ? (Number.isInteger(brandRaw) ? brandRaw : brandRaw.toFixed(1)) : brandRaw;
                    const trendRaw = (fScores.trend !== undefined) ? fScores.trend : ((d.trend_score !== undefined && d.trend_score !== null) ? d.trend_score : (d.candidate_trend_fit_score !== undefined ? d.candidate_trend_fit_score : 0));
                    const trend = typeof trendRaw === 'number' ? (Number.isInteger(trendRaw) ? trendRaw : trendRaw.toFixed(1)) : trendRaw;
                    const commRaw = (fScores.commercial !== undefined) ? fScores.commercial : ((d.commercial_score !== undefined && d.commercial_score !== null) ? d.commercial_score : (d.candidate_commercial_fit !== undefined ? d.candidate_commercial_fit : 0));
                    const comm = typeof commRaw === 'number' ? (Number.isInteger(commRaw) ? commRaw : commRaw.toFixed(1)) : commRaw;
                    const rawProv = (d.availability_provider || '').trim();
                    const isMock = rawProv.toLowerCase().includes('mock') || rawProv.toLowerCase().includes('test');
                    const provider = isMock ? '🧪 TEST — mock provider' : (rawProv ? rawProv : 'Verisign RDAP');
                    
                    let dateStr = 'الآن';
                    if (d.checked_at) {
                        const dt = new Date(d.checked_at);
                        dateStr = `${dt.getDate()} ${dt.toLocaleString('en-US', {month:'short'})} ${dt.getFullYear()} ${dt.getHours().toString().padStart(2,'0')}:${dt.getMinutes().toString().padStart(2,'0')}`;
                    }

                    const desc = d.category || d.reason || 'نطاق تقني مميز متاح للتسجيل العادي.';

                    html += `
                        <div class="ai-domain-card">
                            <div>
                                <div class="ai-domain-card-header">
                                    <h4><i class="fa-solid fa-globe" style="color: #60a5fa; font-size: 1.1rem;"></i> ${dName}</h4>
                                    <span class="overall-score-badge" title="Overall Quality Score">النقاط: ${overall}</span>
                                </div>
                                <div class="domain-scores-grid">
                                    <div class="score-item">
                                        <span class="label">العلامة (Brand)</span>
                                        <span class="val">${brand}</span>
                                    </div>
                                    <div class="score-item">
                                        <span class="label">التريند (Trend)</span>
                                        <span class="val">${trend}</span>
                                    </div>
                                    <div class="score-item">
                                        <span class="label">التجاري (Comm)</span>
                                        <span class="val">${comm}</span>
                                    </div>
                                </div>
                                <div class="badge-verified-available">
                                    <i class="fa-solid fa-circle-check"></i> ✓ متاح للتسجيل العادي (Standard Registration)
                                </div>
                                <div class="domain-concept-desc">${desc}</div>
                            </div>
                            <div class="domain-meta">
                                <span><i class="fa-solid fa-shield-halved"></i> المزود: <b>${provider}</b></span>
                                <span><i class="fa-regular fa-clock"></i> فحص: <b>${dateStr}</b></span>
                            </div>
                        </div>
                    `;
                });
            } else {
                html += `
                    <div style="grid-column: 1/-1; text-align: center; color: #94a3b8; padding: 3rem 1rem; background: rgba(0,0,0,0.2); border-radius: 12px; border: 1px dashed rgba(255,255,255,0.1);">
                        <i class="fa-solid fa-magnifying-glass fa-2x" style="margin-bottom: 1rem; opacity: 0.5;"></i>
                        <p style="font-size: 1.1rem; color: #f8fafc; margin-bottom: 0.5rem;">لا توجد نطاقات مؤكدة حالياً</p>
                        <p style="font-size: 0.9rem; max-width: 500px; margin: 0 auto 1.5rem;">انقر على زر "توليد يدوي" أعلاه لبدء فحص كامل لتريندات اليوم والتحقق من الإتاحة عبر Registry/RDAP.</p>
                    </div>
                `;
            }
            html += `</div>`;
            
            aiContainer.innerHTML = html;
            
        } catch (error) {
            console.error("AI Fetch Error:", error);
            aiContainer.innerHTML = `<div class="error-message" style="grid-column: 1/-1; text-align: center;">
                <i class="fa-solid fa-server fa-2x" style="margin-bottom: 1rem; opacity: 0.8;"></i>
                <br>تعذر تحميل النتائج اليومية. (${error.message})
            </div>`;
        } finally {
            isAILoading = false;
        }
    }

    async function fetchDashboard() {
        initLayout();
        const promises = tier1Countries.map(country => fetchCountryData(country));
        await Promise.all(promises);
        updateTime();
        showToast();
    }

    let statusInterval = null;
    let wasRunning = false;

    const stagesList = [
        'research',
        'concept_extraction',
        'candidate_generation',
        'candidate_validation',
        'availability_check',
        'premium_check',
        'quality_filter',
        'scoring',
        'final_selection',
        'saving_results',
        'completed'
    ];

    const stageDescriptions = {
        'research': 'Starting domain hunt... جمع وتحليل التريندات العالمية',
        'concept_extraction': 'استخراج أفكار ومجالات المشاريع الناشئة',
        'candidate_generation': 'Generating candidates... توليد مرشحي النطاقات',
        'candidate_validation': 'فحص بنية وصيغة النطاقات واستبعاد التالف والمكرر',
        'availability_check': 'Checking availability... فحص الإتاحة عبر Verisign RDAP',
        'premium_check': 'Filtering premium domains... فحص واستبعاد أسعار البريميوم',
        'quality_filter': 'Filtering registered domains... بوابة الإتاحة الصارمة',
        'scoring': 'Scoring verified domains... تقييم العلامة والجدوى',
        'final_selection': 'الاختيار النهائي للفرص المتاحة',
        'saving_results': 'Saving final opportunities... حفظ النتائج المؤكدة',
        'completed': 'Completed. اكتملت المهمة بنجاح!'
    };

    async function checkStatus() {
        try {
            const res = await fetch('/api/domains/status');
            const data = await res.json();
            
            const progressDiv = document.getElementById('ai-job-progress');
            const stageText = document.getElementById('ai-job-stage-text');
            const progressBar = document.getElementById('ai-job-progress-bar');
            const btnManual = document.getElementById('btn-manual-hunt');
            const manualText = document.getElementById('manual-text');
            const manualIcon = document.getElementById('manual-icon');
            
            // Update live counters
            document.getElementById('stat-candidates').innerText = data.candidates_generated || 0;
            document.getElementById('stat-checked').innerText = data.checked || 0;
            document.getElementById('stat-available').innerText = data.available_standard || 0;
            document.getElementById('stat-registered').innerText = data.registered || 0;
            document.getElementById('stat-premium').innerText = data.premium || 0;

            if (data.status === 'running') {
                wasRunning = true;
                progressDiv.style.display = 'block';
                
                if (btnManual) {
                    btnManual.disabled = true;
                    btnManual.style.opacity = '0.6';
                    btnManual.style.cursor = 'not-allowed';
                    if (manualText) manualText.innerText = 'جاري الفحص...';
                    if (manualIcon) manualIcon.className = 'fa-solid fa-spinner fa-spin';
                }

                const currentStage = data.stage || 'research';
                let stageIndex = stagesList.indexOf(currentStage);
                if (stageIndex < 0) stageIndex = 0;

                stageText.innerText = stageDescriptions[currentStage] || currentStage;

                // Colorize pipeline steps
                stagesList.forEach((st, idx) => {
                    const el = document.getElementById('stage-' + st);
                    if (el) {
                        if (idx < stageIndex) {
                            el.style.color = '#10b981'; // completed
                            el.style.fontWeight = 'bold';
                        } else if (idx === stageIndex) {
                            el.style.color = '#fbbf24'; // active
                            el.style.fontWeight = 'bold';
                        } else {
                            el.style.color = '#64748b'; // pending
                            el.style.fontWeight = 'normal';
                        }
                    }
                });

                // Compute progress percentage
                let basePct = (stageIndex / (stagesList.length - 1)) * 100;
                if (currentStage === 'availability_check' && data.candidates_generated > 0) {
                    const checkRatio = Math.min(1.0, data.checked / data.candidates_generated);
                    basePct += checkRatio * 15;
                }
                progressBar.style.width = `${Math.min(basePct, 98)}%`;

            } else {
                // Not running
                if (btnManual) {
                    btnManual.disabled = false;
                    btnManual.style.opacity = '1';
                    btnManual.style.cursor = 'pointer';
                    if (manualText) manualText.innerText = 'توليد يدوي';
                    if (manualIcon) manualIcon.className = 'fa-solid fa-play';
                }

                if (wasRunning) {
                    wasRunning = false;
                    progressBar.style.width = '100%';
                    stageText.innerText = 'Completed. اكتملت المهمة بنجاح!';
                    
                    setTimeout(() => {
                        progressDiv.style.display = 'none';
                        progressBar.style.width = '0%';
                    }, 2500);

                    // Fetch latest verified domains
                    fetchAIDomains();
                    showToast('اكتمل فحص النطاقات وتأكيد الإتاحة بنجاح!');
                } else {
                    progressDiv.style.display = 'none';
                }
            }
        } catch(e) {
            console.error("Status poll error", e);
        }
    }

    function startStatusPolling() {
        if (statusInterval) clearInterval(statusInterval);
        checkStatus();
        statusInterval = setInterval(checkStatus, 2000);
    }

    // Manual Hunt Button Event
    const btnManualHunt = document.getElementById('btn-manual-hunt');
    if (btnManualHunt) {
        btnManualHunt.addEventListener('click', async () => {
            try {
                btnManualHunt.disabled = true;
                const res = await fetch('/api/domains/run', { method: 'POST' });
                const data = await res.json();
                
                if (res.status === 409 || data.status === 'already_running') {
                    alert('عذراً، هناك فحص يعمل بالفعل حالياً في الخلفية.');
                    return;
                }
                
                if (res.ok && data.status === 'started') {
                    showToast('تم بدء فحص النطاقات في الخلفية...');
                    const progressDiv = document.getElementById('ai-job-progress');
                    if (progressDiv) progressDiv.style.display = 'block';
                    checkStatus();
                } else {
                    throw new Error(data.message || 'Server error');
                }
            } catch (err) {
                alert('حدث خطأ أثناء بدء الفحص: ' + err.message);
                btnManualHunt.disabled = false;
            }
        });
    }

    // Event Listeners
    btnRefresh.addEventListener('click', () => {
        clearInterval(refreshInterval);
        clearInterval(aiRefreshInterval);
        fetchDashboard();
        fetchAIDomains();
        startAutoRefresh();
    });

    globalCategory.addEventListener('change', () => {
        btnRefresh.click();
    });

    function startAutoRefresh() {
        refreshInterval = setInterval(() => {
            fetchDashboard();
        }, 60000); // 60 seconds (Countries)
        
        // AI Refresh every 3 minutes
        aiRefreshInterval = setInterval(() => {
            fetchAIDomains();
        }, 180000);
    }

    // Initial Load
    fetchDashboard();
    fetchAIDomains();
    startAutoRefresh();
    startStatusPolling();
});
