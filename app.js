// ═══ SG Game Deals ═══

// ─── Theme toggle ───
const root = document.documentElement;
const toggle = document.getElementById('themeToggle');
const saved = localStorage.getItem('game-theme');
if (saved) root.setAttribute('data-theme', saved);

toggle?.addEventListener('click', () => {
    const next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    root.setAttribute('data-theme', next);
    localStorage.setItem('game-theme', next);
});

// ─── i18n (中英文切换) ───
const i18n = {
    en: {
        'nav.about': 'About',
        'nav.posts': 'Guides',
        'intro.badge': 'Fresh deals daily',
        'intro.tagline': 'Singapore gaming deals & steals, <em>updated every day.</em>',
        'intro.bio': 'Switch drops, PS5 restocks, game sales, and all the deals worth your time. Curated from across the island.',
        'blog.recent': 'Recent Guides',
        'deals.title': 'Today\'s Deals',
        'deals.subtitle': 'Curated from social media — Switch drops, PS5 restocks, game sales & flash promos',
        'deals.viewSource': 'View source →',
        'preview.allPosts': 'View all',
        'preview.allDeals': 'View all deals',
        'about.title': 'About',
        'about.p1': 'SG Game Deals is a daily-updated blog that rounds up the best gaming deals, promos, and steals across Singapore.',
        'about.p2': 'From Nintendo Switch drops to PS5 restocks, eShop sales to Xbox bargains — if it\'s a deal worth sharing, it\'s here. We expand country by country.',
        'about.p3': 'Updated daily by an AI agent scanning social media.',
        'lang.switchTo': '中文',
        'country.all': 'All Countries',
    },
    zh: {
        'nav.about': '关于',
        'nav.posts': '攻略',
        'intro.badge': '每日更新好价',
        'intro.tagline': '新加坡游戏优惠，<em>每天更新。</em>',
        'intro.bio': 'Switch 降价、PS5 补货、游戏特卖，所有值得关注的优惠都在这里。精选全岛好价。',
        'blog.recent': '最新攻略',
        'deals.title': '今日优惠',
        'deals.subtitle': '精选自社交媒体——Switch 降价、PS5 补货、游戏特卖与限时促销',
        'deals.viewSource': '查看来源 →',
        'preview.allPosts': '查看全部',
        'preview.allDeals': '查看全部优惠',
        'about.title': '关于',
        'about.p1': 'SG Game Deals 是一个每日更新的博客，汇总新加坡最划算的游戏优惠、促销和好价。',
        'about.p2': '从 Nintendo Switch 降价到 PS5 补货，从 eShop 特卖到 Xbox 好价——只要是值得分享的优惠，都在这里。我们会逐步扩展到更多国家。',
        'about.p3': '每天由 AI 智能体从社交媒体精选更新。',
        'lang.switchTo': 'EN',
        'country.all': '全部国家',
    }
};

function detectLang() {
    const saved = localStorage.getItem('game-lang');
    if (saved && i18n[saved]) return saved;
    const browserLang = navigator.language || navigator.userLanguage || 'en';
    return browserLang.toLowerCase().startsWith('zh') ? 'zh' : 'en';
}

function applyLang(lang) {
    const strings = i18n[lang] || i18n.en;

    // 1. data-i18n — UI strings (textContent)
    document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');
        if (strings[key]) el.textContent = strings[key];
    });

    // 2. data-i18n-html — UI strings with HTML (innerHTML)
    document.querySelectorAll('[data-i18n-html]').forEach(el => {
        const key = el.getAttribute('data-i18n-html');
        if (strings[key]) el.innerHTML = strings[key];
    });

    // 3. data-en / data-zh — inline content translation
    document.querySelectorAll('[data-en][data-zh]').forEach(el => {
        el.innerHTML = el.getAttribute('data-' + lang) || el.getAttribute('data-en');
    });

    // 4. Deal cards "View source"
    document.querySelectorAll('.deal-open').forEach(el => {
        el.textContent = strings['deals.viewSource'];
    });

    document.documentElement.setAttribute('lang', lang);

    const langLabel = document.querySelector('.lang-label');
    if (langLabel) langLabel.textContent = lang === 'en' ? '中文' : 'EN';
}

let currentLang = detectLang();
applyLang(currentLang);

const langToggle = document.getElementById('langToggle');
langToggle?.addEventListener('click', () => {
    currentLang = currentLang === 'en' ? 'zh' : 'en';
    localStorage.setItem('game-lang', currentLang);
    applyLang(currentLang);
});

// ─── Feed tabs (Preview | Posts | Deals) ───
function switchFeed(target) {
    document.querySelectorAll('.feed-tabs .tab-btn').forEach(b => {
        b.classList.toggle('active', b.dataset.feed === target);
    });
    document.querySelectorAll('.tab-pane').forEach(pane => {
        pane.classList.toggle('active', pane.id === 'pane-' + target);
    });
    localStorage.setItem('game-feed', target);
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

document.querySelectorAll('.feed-tabs .tab-btn').forEach(btn => {
    btn.addEventListener('click', () => switchFeed(btn.dataset.feed));
});

document.querySelectorAll('.preview-more').forEach(btn => {
    btn.addEventListener('click', () => switchFeed(btn.dataset.feed));
});

const savedFeed = localStorage.getItem('game-feed');
if (savedFeed === 'posts' || savedFeed === 'deals') {
    switchFeed(savedFeed);
}

// ─── Country filter ───
document.querySelectorAll('.country-pill').forEach(pill => {
    pill.addEventListener('click', () => {
        document.querySelectorAll('.country-pill').forEach(p => p.classList.remove('active'));
        pill.classList.add('active');
        const country = pill.dataset.country;
        // Filter deal cards
        document.querySelectorAll('.deal-card').forEach(card => {
            if (country === 'all' || card.dataset.country === country) {
                card.style.display = '';
            } else {
                card.style.display = 'none';
            }
        });
        // Filter post items
        document.querySelectorAll('.post-item').forEach(card => {
            if (country === 'all' || card.dataset.country === country) {
                card.style.display = '';
            } else {
                card.style.display = 'none';
            }
        });
    });
});

// ─── Image lightbox ───
(function() {
    const overlay = document.createElement('div');
    overlay.className = 'lightbox-overlay';
    overlay.innerHTML = `
        <button class="lightbox-close" aria-label="Close">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="18" y1="6" x2="6" y2="18"/>
                <line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
        </button>
        <img src="" alt="" />
    `;
    document.body.appendChild(overlay);

    const lbImg = overlay.querySelector('img');
    const lbClose = overlay.querySelector('.lightbox-close');

    function open(src) {
        lbImg.src = src;
        overlay.classList.add('active');
        document.body.style.overflow = 'hidden';
    }
    function close() {
        overlay.classList.remove('active');
        document.body.style.overflow = '';
    }

    document.addEventListener('click', (e) => {
        const mediaLink = e.target.closest('.deal-media');
        if (mediaLink) {
            e.preventDefault();
            const full = mediaLink.getAttribute('data-full') || mediaLink.querySelector('img')?.src;
            if (full) open(full);
        }
    });

    overlay.addEventListener('click', (e) => {
        if (e.target === overlay || e.target.closest('.lightbox-close')) close();
    });
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') close();
    });
})();

// ─── Nav scroll state ───
const nav = document.querySelector('.nav');
window.addEventListener('scroll', () => {
    if (window.scrollY > 20) nav?.classList.add('scrolled');
    else nav?.classList.remove('scrolled');
}, { passive: true });

// ─── Nav dropdown menu ───
(function() {
    const menuBtn = document.getElementById('navMenuBtn');
    const dropdown = document.getElementById('navDropdown');
    if (!menuBtn || !dropdown) return;

    menuBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        dropdown.classList.toggle('open');
    });

    // Close on outside click
    document.addEventListener('click', (e) => {
        if (!e.target.closest('#navDropdown') && !e.target.closest('#navMenuBtn')) {
            dropdown.classList.remove('open');
        }
    });

    // Close on Escape
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') dropdown.classList.remove('open');
    });
})();

// ─── Reading progress bar ───
const progress = document.querySelector('.progress-bar');
window.addEventListener('scroll', () => {
    if (!progress) return;
    const winHeight = document.documentElement.scrollHeight - window.innerHeight;
    const scrolled = (window.scrollY / winHeight) * 100;
    progress.style.width = Math.min(scrolled, 100) + '%';
}, { passive: true });

// ─── Newsletter form ───
// Replace FORMSPREE_ENDPOINT with your Formspree form URL after signup
const FORMSPREE_ENDPOINT = 'https://formspree.io/f/mqervnja';

(function() {
    const form = document.getElementById('newsletterForm');
    const success = document.getElementById('newsletterSuccess');
    if (!form || !success) return;

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const email = form.querySelector('input[type="email"]').value.trim();
        if (!email) return;

        const btn = form.querySelector('button');
        const origText = btn.textContent;
        btn.textContent = '...';
        btn.disabled = true;

        try {
            // Try Formspree — if endpoint not configured yet, simulate success
            if (FORMSPREE_ENDPOINT.includes('YOUR_FORM_ID')) {
                // Demo mode — no backend yet, just show success
                localStorage.setItem('newsletter_email', email);
                await new Promise(r => setTimeout(r, 600));
            } else {
                const res = await fetch(FORMSPREE_ENDPOINT, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
                    body: JSON.stringify({ email, _subject: 'New newsletter signup', source: 'sg-game-deals' })
                });
                if (!res.ok) throw new Error('Submit failed');
            }
            form.style.display = 'none';
            success.classList.add('show');
        } catch (err) {
            btn.textContent = origText;
            btn.disabled = false;
            alert('Something went wrong. Please try again.');
        }
    });
})();
