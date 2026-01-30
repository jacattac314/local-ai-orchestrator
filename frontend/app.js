/**
 * AI Orchestrator Dashboard
 * Interactive frontend for the routing API
 */

// API URL Configuration
// Priority: 1. Local API (localhost:8080), 2. Docker proxy, 3. Demo mode
const isGitHubPages = window.location.hostname.includes('github.io');
const isDocker = window.location.port === '3000' || window.location.pathname.startsWith('/api');

// For local development, try the API first
const LOCAL_API_URL = 'http://localhost:8082';
const DOCKER_API_URL = '/api';

// Detect which API to use
let API_BASE = null;
let DEMO_MODE = true;

// Try to detect live API on load
async function detectAPI() {
    if (isGitHubPages) {
        console.log('Running on GitHub Pages - using demo mode');
        return null;
    }
    
    if (isDocker) {
        console.log('Running in Docker - using /api proxy');
        return DOCKER_API_URL;
    }
    
    // Try local API
    try {
        const response = await fetch(LOCAL_API_URL + '/health', { 
            method: 'GET',
            mode: 'cors',
            timeout: 2000 
        });
        if (response.ok) {
            console.log('Local API detected at ' + LOCAL_API_URL);
            return LOCAL_API_URL;
        }
    } catch (e) {
        console.log('Local API not available, using demo mode');
    }
    
    return null;
}

// Initialize API detection
detectAPI().then(url => {
    API_BASE = url;
    DEMO_MODE = url === null;
    console.log('API Mode:', DEMO_MODE ? 'DEMO' : 'LIVE', 'URL:', API_BASE);
    
    // Reload data with detected API
    if (!DEMO_MODE && state.currentPage === 'dashboard') {
        loadDashboard();
    }
});

// State
const state = {
    currentPage: 'dashboard',
    activeProfile: 'balanced',
    models: [],
    profiles: {},
    rankings: [],
};

// DOM Elements
const elements = {
    pages: {},
    navItems: null,
    pageTitle: null,
    activeProfile: null,
    refreshBtn: null,
};

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    initElements();
    initNavigation();
    initEventListeners();
    loadDashboard();
});

function initElements() {
    elements.pages = {
        dashboard: document.getElementById('dashboardPage'),
        models: document.getElementById('modelsPage'),
        routing: document.getElementById('routingPage'),
        analytics: document.getElementById('analyticsPage'),
        playground: document.getElementById('playgroundPage'),
    };
    elements.navItems = document.querySelectorAll('.nav-item');
    elements.pageTitle = document.querySelector('.page-title');
    elements.activeProfile = document.getElementById('activeProfile');
    elements.refreshBtn = document.getElementById('refreshBtn');
}

function initNavigation() {
    elements.navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const page = item.dataset.page;
            navigateTo(page);
        });
    });
}

function navigateTo(page) {
    // Update nav
    elements.navItems.forEach(item => {
        item.classList.toggle('active', item.dataset.page === page);
    });
    
    // Update pages
    Object.entries(elements.pages).forEach(([key, el]) => {
        el.classList.toggle('hidden', key !== page);
    });
    
    // Update title
    const titles = {
        dashboard: 'Dashboard',
        models: 'Models',
        routing: 'Routing',
        analytics: 'Analytics',
        playground: 'Playground',
    };
    elements.pageTitle.textContent = titles[page];
    
    state.currentPage = page;
    
    // Load page data
    if (page === 'models') loadModels();
    if (page === 'routing') loadRouting();
    if (page === 'analytics') loadAnalytics();
}

function initEventListeners() {
    elements.refreshBtn.addEventListener('click', () => {
        loadDashboard();
        showToast('Data refreshed');
    });
    
    elements.activeProfile.addEventListener('change', (e) => {
        state.activeProfile = e.target.value;
        loadRankings();
    });
    
    const analyzeBtn = document.getElementById('analyzeBtn');
    if (analyzeBtn) {
        analyzeBtn.addEventListener('click', analyzePrompt);
    }
    
    const modelSearch = document.getElementById('modelSearch');
    if (modelSearch) {
        modelSearch.addEventListener('input', (e) => {
            filterModels(e.target.value);
        });
    }
}

// Demo data for GitHub Pages (no live API needed)
const DEMO_DATA = {
    health: { status: 'healthy', model_count: 156, db_status: 'connected' },
    rankings: {
        rankings: [
            { model_id: 1, model_name: 'openai/gpt-4-turbo', composite_score: 0.94, quality_score: 0.98, latency_score: 0.85, cost_score: 0.72 },
            { model_id: 2, model_name: 'anthropic/claude-3-opus', composite_score: 0.91, quality_score: 0.96, latency_score: 0.82, cost_score: 0.68 },
            { model_id: 3, model_name: 'anthropic/claude-3-sonnet', composite_score: 0.88, quality_score: 0.92, latency_score: 0.88, cost_score: 0.78 },
            { model_id: 4, model_name: 'openai/gpt-4o', composite_score: 0.86, quality_score: 0.94, latency_score: 0.90, cost_score: 0.65 },
            { model_id: 5, model_name: 'google/gemini-1.5-pro', composite_score: 0.84, quality_score: 0.90, latency_score: 0.85, cost_score: 0.72 },
            { model_id: 6, model_name: 'meta-llama/llama-3-70b', composite_score: 0.82, quality_score: 0.85, latency_score: 0.80, cost_score: 0.92 },
            { model_id: 7, model_name: 'anthropic/claude-3-haiku', composite_score: 0.79, quality_score: 0.82, latency_score: 0.95, cost_score: 0.88 },
            { model_id: 8, model_name: 'openai/gpt-3.5-turbo', composite_score: 0.75, quality_score: 0.78, latency_score: 0.92, cost_score: 0.95 },
            { model_id: 9, model_name: 'mistral/mistral-large', composite_score: 0.73, quality_score: 0.80, latency_score: 0.82, cost_score: 0.85 },
            { model_id: 10, model_name: 'cohere/command-r-plus', composite_score: 0.70, quality_score: 0.76, latency_score: 0.78, cost_score: 0.88 },
        ]
    },
    profiles: {
        profiles: {
            balanced: { quality_weight: 0.4, latency_weight: 0.3, cost_weight: 0.3 },
            quality: { quality_weight: 0.7, latency_weight: 0.2, cost_weight: 0.1, min_quality: 0.8 },
            speed: { quality_weight: 0.2, latency_weight: 0.6, cost_weight: 0.2, max_latency_ms: 500 },
            budget: { quality_weight: 0.2, latency_weight: 0.2, cost_weight: 0.6, max_cost_per_million: 5.0 },
            long_context: { quality_weight: 0.3, latency_weight: 0.2, cost_weight: 0.2 },
        }
    },
    models: {
        models: [
            { name: 'openai/gpt-4-turbo', quality_score: 0.98, latency_ms: 450, cost_per_million: 10.0, context_length: 128000 },
            { name: 'anthropic/claude-3-opus', quality_score: 0.96, latency_ms: 520, cost_per_million: 15.0, context_length: 200000 },
            { name: 'anthropic/claude-3-sonnet', quality_score: 0.92, latency_ms: 380, cost_per_million: 3.0, context_length: 200000 },
            { name: 'openai/gpt-4o', quality_score: 0.94, latency_ms: 320, cost_per_million: 5.0, context_length: 128000 },
            { name: 'google/gemini-1.5-pro', quality_score: 0.90, latency_ms: 400, cost_per_million: 3.5, context_length: 1000000 },
            { name: 'meta-llama/llama-3-70b', quality_score: 0.85, latency_ms: 480, cost_per_million: 0.9, context_length: 8192 },
            { name: 'anthropic/claude-3-haiku', quality_score: 0.82, latency_ms: 180, cost_per_million: 0.25, context_length: 200000 },
            { name: 'openai/gpt-3.5-turbo', quality_score: 0.78, latency_ms: 200, cost_per_million: 0.5, context_length: 16384 },
        ]
    }
};

// API Calls
async function fetchAPI(endpoint) {
    // Demo mode - return static data
    if (DEMO_MODE) {
        await new Promise(r => setTimeout(r, 300)); // Simulate network delay
        if (endpoint.includes('/health')) return DEMO_DATA.health;
        if (endpoint.includes('/rankings')) return DEMO_DATA.rankings;
        if (endpoint.includes('/routing_profiles')) return DEMO_DATA.profiles;
        if (endpoint.includes('/models')) return DEMO_DATA.models;
        return null;
    }
    
    try {
        const response = await fetch(`${API_BASE}${endpoint}`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return await response.json();
    } catch (error) {
        console.error(`API Error: ${endpoint}`, error);
        return null;
    }
}

async function postAPI(endpoint, data) {
    if (DEMO_MODE) {
        await new Promise(r => setTimeout(r, 300));
        return DEMO_DATA.rankings; // Return demo rankings for playground
    }
    
    try {
        const response = await fetch(`${API_BASE}${endpoint}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return await response.json();
    } catch (error) {
        console.error(`API Error: ${endpoint}`, error);
        return null;
    }
}

// Dashboard
async function loadDashboard() {
    await Promise.all([
        loadHealth(),
        loadRankings(),
        loadProfiles(),
    ]);
}

async function loadHealth() {
    const health = await fetchAPI('/health');
    if (health) {
        document.getElementById('totalModels').textContent = health.model_count || '0';
        document.getElementById('healthyCount').textContent = health.model_count || '0';
    }
    
    // Set placeholder stats
    document.getElementById('avgLatency').textContent = '245ms';
    document.getElementById('avgCost').textContent = '$2.40';
}

async function loadRankings() {
    const rankingsEl = document.getElementById('rankingsList');
    
    const rankings = await fetchAPI(`/v1/models/rankings?profile=${state.activeProfile}&limit=10`);
    
    if (!rankings || !rankings.rankings) {
        rankingsEl.innerHTML = `
            <div class="empty-state">
                <p>No rankings available</p>
            </div>
        `;
        return;
    }
    
    state.rankings = rankings.rankings;
    
    rankingsEl.innerHTML = rankings.rankings.map((model, index) => `
        <div class="ranking-item">
            <div class="ranking-position ${index < 3 ? 'top-3' : ''}">${index + 1}</div>
            <div class="ranking-info">
                <span class="ranking-name">${formatModelName(model.model_name)}</span>
                <span class="ranking-provider">${getProvider(model.model_name)}</span>
            </div>
            <div class="ranking-score">
                <div class="score-bar">
                    <div class="score-fill" style="width: ${model.composite_score * 100}%"></div>
                </div>
                <span class="score-value">${(model.composite_score * 100).toFixed(0)}%</span>
            </div>
        </div>
    `).join('');
}

async function loadProfiles() {
    const profilesEl = document.getElementById('profilesGrid');
    
    const data = await fetchAPI('/v1/routing_profiles');
    
    if (!data || !data.profiles) {
        profilesEl.innerHTML = '<p>Failed to load profiles</p>';
        return;
    }
    
    state.profiles = data.profiles;
    
    profilesEl.innerHTML = Object.entries(data.profiles).map(([name, profile]) => `
        <div class="profile-card ${name === state.activeProfile ? 'active' : ''}" 
             onclick="selectProfile('${name}')">
            <div class="profile-card-header">
                <span class="profile-card-name">${name}</span>
                ${getProfileIcon(name)}
            </div>
            <div class="profile-weights">
                <div class="weight-bar">
                    <div class="weight-fill quality" style="width: ${profile.quality_weight * 100}%"></div>
                </div>
                <div class="weight-bar">
                    <div class="weight-fill latency" style="width: ${profile.latency_weight * 100}%"></div>
                </div>
                <div class="weight-bar">
                    <div class="weight-fill cost" style="width: ${profile.cost_weight * 100}%"></div>
                </div>
            </div>
        </div>
    `).join('');
}

function selectProfile(name) {
    state.activeProfile = name;
    elements.activeProfile.value = name;
    loadRankings();
    loadProfiles();
}

// Models Page
async function loadModels() {
    const tbody = document.getElementById('modelsTableBody');
    
    const data = await fetchAPI('/v1/models');
    
    if (!data || !data.models) {
        tbody.innerHTML = '<tr><td colspan="7">Failed to load models</td></tr>';
        return;
    }
    
    state.models = data.models;
    renderModelsTable(data.models);
}

function renderModelsTable(models) {
    const tbody = document.getElementById('modelsTableBody');
    
    tbody.innerHTML = models.map(model => `
        <tr>
            <td><strong>${formatModelName(model.name)}</strong></td>
            <td>${getProvider(model.name)}</td>
            <td>${model.quality_score ? (model.quality_score * 100).toFixed(0) + '%' : '-'}</td>
            <td>${model.latency_ms ? model.latency_ms + 'ms' : '-'}</td>
            <td>${model.cost_per_million ? '$' + model.cost_per_million.toFixed(2) : '-'}</td>
            <td>${model.context_length ? formatNumber(model.context_length) : '-'}</td>
            <td><span class="status-tag healthy">Healthy</span></td>
        </tr>
    `).join('');
}

function filterModels(query) {
    const filtered = state.models.filter(m => 
        m.name.toLowerCase().includes(query.toLowerCase())
    );
    renderModelsTable(filtered);
}

// Routing Page
async function loadRouting() {
    const configEl = document.getElementById('profileConfig');
    const chartEl = document.getElementById('weightsChart');
    
    const profile = state.profiles[state.activeProfile];
    
    if (!profile) {
        configEl.innerHTML = '<p>Select a profile</p>';
        return;
    }
    
    configEl.innerHTML = `
        <div class="config-group">
            <label class="config-label">Quality Weight: ${(profile.quality_weight * 100).toFixed(0)}%</label>
            <input type="range" class="config-slider" value="${profile.quality_weight * 100}" 
                   min="0" max="100" disabled>
        </div>
        <div class="config-group">
            <label class="config-label">Latency Weight: ${(profile.latency_weight * 100).toFixed(0)}%</label>
            <input type="range" class="config-slider" value="${profile.latency_weight * 100}" 
                   min="0" max="100" disabled>
        </div>
        <div class="config-group">
            <label class="config-label">Cost Weight: ${(profile.cost_weight * 100).toFixed(0)}%</label>
            <input type="range" class="config-slider" value="${profile.cost_weight * 100}" 
                   min="0" max="100" disabled>
        </div>
        ${profile.min_quality ? `
        <div class="config-group">
            <label class="config-label">Min Quality: ${(profile.min_quality * 100).toFixed(0)}%</label>
        </div>
        ` : ''}
        ${profile.max_latency_ms ? `
        <div class="config-group">
            <label class="config-label">Max Latency: ${profile.max_latency_ms}ms</label>
        </div>
        ` : ''}
    `;
    
    // Render chart
    chartEl.innerHTML = renderWeightsChart(profile);
}

function renderWeightsChart(profile) {
    const total = profile.quality_weight + profile.latency_weight + profile.cost_weight;
    const q = (profile.quality_weight / total) * 100;
    const l = (profile.latency_weight / total) * 100;
    const c = (profile.cost_weight / total) * 100;
    
    return `
        <svg viewBox="0 0 200 200" style="width: 200px; height: 200px;">
            <circle cx="100" cy="100" r="80" fill="none" stroke="var(--border)" stroke-width="20"/>
            <circle cx="100" cy="100" r="80" fill="none" stroke="var(--accent-blue)" stroke-width="20"
                    stroke-dasharray="${q * 5.02} ${500 - q * 5.02}" 
                    stroke-dashoffset="125" transform="rotate(-90 100 100)"/>
            <circle cx="100" cy="100" r="80" fill="none" stroke="var(--accent-green)" stroke-width="20"
                    stroke-dasharray="${l * 5.02} ${500 - l * 5.02}" 
                    stroke-dashoffset="${125 - q * 5.02}" transform="rotate(-90 100 100)"/>
            <circle cx="100" cy="100" r="80" fill="none" stroke="var(--accent-orange)" stroke-width="20"
                    stroke-dasharray="${c * 5.02} ${500 - c * 5.02}" 
                    stroke-dashoffset="${125 - q * 5.02 - l * 5.02}" transform="rotate(-90 100 100)"/>
            <text x="100" y="95" text-anchor="middle" fill="var(--text-primary)" font-size="20" font-weight="600">
                ${state.activeProfile}
            </text>
            <text x="100" y="115" text-anchor="middle" fill="var(--text-muted)" font-size="12">
                Profile
            </text>
        </svg>
        <div style="display: flex; gap: var(--space-lg); margin-top: var(--space-lg);">
            <div style="display: flex; align-items: center; gap: var(--space-sm);">
                <div style="width: 12px; height: 12px; background: var(--accent-blue); border-radius: 2px;"></div>
                <span style="font-size: 0.875rem; color: var(--text-secondary);">Quality</span>
            </div>
            <div style="display: flex; align-items: center; gap: var(--space-sm);">
                <div style="width: 12px; height: 12px; background: var(--accent-green); border-radius: 2px;"></div>
                <span style="font-size: 0.875rem; color: var(--text-secondary);">Latency</span>
            </div>
            <div style="display: flex; align-items: center; gap: var(--space-sm);">
                <div style="width: 12px; height: 12px; background: var(--accent-orange); border-radius: 2px;"></div>
                <span style="font-size: 0.875rem; color: var(--text-secondary);">Cost</span>
            </div>
        </div>
    `;
}

// Playground
async function analyzePrompt() {
    const promptInput = document.getElementById('promptInput');
    const resultEl = document.getElementById('routingResult');
    const profile = document.getElementById('testProfile').value;
    
    const prompt = promptInput.value.trim();
    
    if (!prompt) {
        showToast('Please enter a prompt', 'warning');
        return;
    }
    
    resultEl.innerHTML = `
        <div class="loading-skeleton">
            <div class="skeleton-card"></div>
            <div class="skeleton-row"></div>
        </div>
    `;
    
    // Simulate routing analysis (use actual API when available)
    const rankings = await fetchAPI(`/v1/models/rankings?profile=${profile}&limit=3`);
    
    if (!rankings || !rankings.rankings || rankings.rankings.length === 0) {
        resultEl.innerHTML = `
            <div class="empty-state">
                <p>No routing result available</p>
            </div>
        `;
        return;
    }
    
    const selectedModel = rankings.rankings[0];
    
    resultEl.innerHTML = `
        <div class="result-card">
            <div class="result-card-header">
                <span class="result-card-title">${formatModelName(selectedModel.model_name)}</span>
                <span class="badge">${profile}</span>
            </div>
            <p style="color: var(--text-secondary); font-size: 0.875rem;">
                Selected as the optimal model for your request based on the ${profile} profile.
            </p>
            <div class="result-metrics">
                <div class="result-metric">
                    <div class="result-metric-value">${(selectedModel.composite_score * 100).toFixed(0)}%</div>
                    <div class="result-metric-label">Score</div>
                </div>
                <div class="result-metric">
                    <div class="result-metric-value">${(selectedModel.quality_score * 100).toFixed(0)}%</div>
                    <div class="result-metric-label">Quality</div>
                </div>
                <div class="result-metric">
                    <div class="result-metric-value">${(selectedModel.latency_score * 100).toFixed(0)}%</div>
                    <div class="result-metric-label">Latency</div>
                </div>
            </div>
        </div>
        
        <h3 style="margin: var(--space-lg) 0 var(--space-md); font-size: 0.9375rem; color: var(--text-secondary);">
            Fallback Options
        </h3>
        
        ${rankings.rankings.slice(1).map((model, i) => `
            <div class="ranking-item" style="background: var(--bg-tertiary); border-radius: var(--radius-md); margin-bottom: var(--space-sm);">
                <div class="ranking-position">${i + 2}</div>
                <div class="ranking-info">
                    <span class="ranking-name">${formatModelName(model.model_name)}</span>
                    <span class="ranking-provider">${getProvider(model.model_name)}</span>
                </div>
                <div class="ranking-score">
                    <span class="score-value">${(model.composite_score * 100).toFixed(0)}%</span>
                </div>
            </div>
        `).join('')}
    `;
}

// Helpers
function formatModelName(name) {
    // Extract model name from provider/model format
    const parts = name.split('/');
    return parts.length > 1 ? parts[1] : name;
}

function getProvider(name) {
    const parts = name.split('/');
    if (parts.length > 1) {
        return parts[0].charAt(0).toUpperCase() + parts[0].slice(1);
    }
    return 'Unknown';
}

function formatNumber(num) {
    if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
    if (num >= 1000) return (num / 1000).toFixed(0) + 'K';
    return num.toString();
}

function getProfileIcon(name) {
    const icons = {
        quality: '<svg class="profile-card-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>',
        balanced: '<svg class="profile-card-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>',
        speed: '<svg class="profile-card-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>',
        budget: '<svg class="profile-card-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>',
        long_context: '<svg class="profile-card-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>',
    };
    return icons[name] || icons.balanced;
}

function showToast(message, type = 'success') {
    // Simple toast notification
    const existing = document.querySelector('.toast');
    if (existing) existing.remove();
    
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    toast.style.cssText = `
        position: fixed;
        bottom: 24px;
        right: 24px;
        background: var(--bg-tertiary);
        color: var(--text-primary);
        padding: 12px 20px;
        border-radius: 8px;
        font-size: 0.875rem;
        border: 1px solid var(--border);
        box-shadow: var(--shadow-lg);
        z-index: 1000;
        animation: slideIn 0.3s ease;
    `;
    
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}

// Make selectProfile available globally
window.selectProfile = selectProfile;

// Analytics Page
async function loadAnalytics() {
    const period = document.getElementById('analyticsPeriod')?.value || '24h';
    
    // In demo mode, use static data
    if (DEMO_MODE) {
        document.getElementById('totalRequests').textContent = '1,247';
        document.getElementById('totalTokens').textContent = '2.3M';
        document.getElementById('estimatedCost').textContent = '$45.80';
        document.getElementById('analyticsLatency').textContent = '312ms';
        return;
    }
    
    // Fetch real analytics data
    const summary = await fetchAPI(`/v1/analytics/summary?period=${period}`);
    
    if (summary) {
        document.getElementById('totalRequests').textContent = formatNumber(summary.total_requests);
        document.getElementById('totalTokens').textContent = formatNumber(summary.total_tokens);
        document.getElementById('estimatedCost').textContent = `$${summary.estimated_cost.toFixed(2)}`;
        document.getElementById('analyticsLatency').textContent = `${Math.round(summary.avg_latency_ms)}ms`;
        
        // Update model breakdown if available
        if (summary.top_models && summary.top_models.length > 0) {
            const breakdownEl = document.getElementById('modelBreakdown');
            const total = summary.top_models.reduce((a, m) => a + m.count, 0);
            
            breakdownEl.innerHTML = summary.top_models.slice(0, 5).map((model, idx) => {
                const percent = total > 0 ? ((model.count / total) * 100).toFixed(0) : 0;
                const colors = ['var(--accent-blue)', 'var(--accent-purple)', 'var(--accent-green)', 'var(--accent-orange)', 'var(--text-muted)'];
                return `
                    <div class="breakdown-item">
                        <div class="breakdown-label">
                            <span class="breakdown-name">${formatModelName(model.model)}</span>
                            <span class="breakdown-percent">${percent}%</span>
                        </div>
                        <div class="breakdown-bar">
                            <div class="breakdown-fill" style="width: ${percent}%; background: ${colors[idx % colors.length]};"></div>
                        </div>
                    </div>
                `;
            }).join('');
        }
        
        // Update profile usage if available
        if (summary.requests_by_profile) {
            const profileEl = document.getElementById('profileUsage');
            const total = Object.values(summary.requests_by_profile).reduce((a, b) => a + b, 0);
            
            profileEl.innerHTML = Object.entries(summary.requests_by_profile).map(([name, count]) => {
                const percent = total > 0 ? ((count / total) * 100).toFixed(0) : 0;
                return `
                    <div class="profile-usage-card">
                        <div class="profile-usage-value">${percent}%</div>
                        <div class="profile-usage-name">${name}</div>
                    </div>
                `;
            }).join('');
        }
    }
}

// Add event listener for analytics period change
document.addEventListener('DOMContentLoaded', () => {
    const analyticsPeriod = document.getElementById('analyticsPeriod');
    if (analyticsPeriod) {
        analyticsPeriod.addEventListener('change', loadAnalytics);
    }
    
    // Initialize custom model modal
    initAddModelModal();
});

// Custom Model Modal
function initAddModelModal() {
    const modal = document.getElementById('addModelModal');
    const addBtn = document.getElementById('addModelBtn');
    const closeBtn = document.getElementById('closeModalBtn');
    const cancelBtn = document.getElementById('cancelModalBtn');
    const form = document.getElementById('addModelForm');
    
    if (!modal || !addBtn) return;
    
    // Open modal
    addBtn.addEventListener('click', () => {
        modal.classList.add('active');
    });
    
    // Close modal
    const closeModal = () => {
        modal.classList.remove('active');
        form.reset();
    };
    
    closeBtn?.addEventListener('click', closeModal);
    cancelBtn?.addEventListener('click', closeModal);
    
    // Close on overlay click
    modal.addEventListener('click', (e) => {
        if (e.target === modal) closeModal();
    });
    
    // Close on escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && modal.classList.contains('active')) {
            closeModal();
        }
    });
    
    // Form submission
    form?.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        if (DEMO_MODE) {
            alert('Custom models require the API to be running.\nStart the API with: python -m uvicorn orchestrator.api.app:app --port 8080');
            return;
        }
        
        const formData = new FormData(form);
        const modelData = {
            model_name: formData.get('model_name'),
            cost_per_million: parseFloat(formData.get('cost_per_million')) || 0,
            latency_ms: formData.get('latency_ms') ? parseFloat(formData.get('latency_ms')) : null,
            context_length: formData.get('context_length') ? parseInt(formData.get('context_length')) : null,
            quality_rating: formData.get('quality_rating') ? parseFloat(formData.get('quality_rating')) : null,
        };
        
        try {
            const response = await fetch(`${API_BASE}/v1/models/custom`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(modelData),
            });
            
            const result = await response.json();
            
            if (response.ok) {
                closeModal();
                showNotification(`Model "${modelData.model_name}" added successfully!`, 'success');
                // Refresh rankings to show new model
                loadDashboard();
            } else {
                showNotification(result.detail || 'Failed to add model', 'error');
            }
        } catch (error) {
            console.error('Error adding model:', error);
            showNotification('Failed to add model. Is the API running?', 'error');
        }
    });
}

// Simple notification function
function showNotification(message, type = 'info') {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.innerHTML = `
        <span>${message}</span>
        <button onclick="this.parentElement.remove()">&times;</button>
    `;
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 12px 16px;
        border-radius: 8px;
        background: ${type === 'success' ? '#10b981' : type === 'error' ? '#ef4444' : '#3b82f6'};
        color: white;
        display: flex;
        align-items: center;
        gap: 12px;
        z-index: 2000;
        animation: slideIn 0.2s ease;
        box-shadow: 0 4px 12px rgba(0,0,0,0.2);
    `;
    
    document.body.appendChild(notification);
    
    // Auto-remove after 4 seconds
    setTimeout(() => {
        notification.style.animation = 'slideOut 0.2s ease';
        setTimeout(() => notification.remove(), 200);
    }, 4000);
}

// ===== Budget Management =====

// Demo budget data for GitHub Pages
const DEMO_BUDGET = {
    config: {
        daily_limit: 10.0,
        weekly_limit: 50.0,
        monthly_limit: 100.0,
        alert_threshold: 0.8,
        hard_limit: false
    },
    spend: {
        daily_spend: 3.45,
        weekly_spend: 18.72,
        monthly_spend: 45.80,
        daily_remaining: 6.55,
        weekly_remaining: 31.28,
        monthly_remaining: 54.20,
        daily_percent: 34.5,
        weekly_percent: 37.4,
        monthly_percent: 45.8
    },
    status: 'ok',
    status_message: 'All spending within limits',
    enforcement: 'advisory'
};

async function loadBudgetStatus() {
    let budgetData;
    
    if (DEMO_MODE) {
        await new Promise(r => setTimeout(r, 300));
        budgetData = DEMO_BUDGET;
    } else {
        budgetData = await fetchAPI('/v1/budget');
    }
    
    if (!budgetData) return;
    
    // Update budget widget in header
    updateBudgetWidget(budgetData);
    
    // Update settings page if visible
    if (state.currentPage === 'settings') {
        updateBudgetSettings(budgetData);
    }
}

function updateBudgetWidget(data) {
    const widget = document.getElementById('budgetWidget');
    const valueEl = document.getElementById('budgetWidgetValue');
    const fillEl = document.getElementById('budgetWidgetFill');
    
    if (!widget || !valueEl || !fillEl) return;
    
    const spend = data.spend || {};
    const dailySpend = spend.daily_spend || 0;
    const dailyPercent = spend.daily_percent || 0;
    
    valueEl.textContent = `$${dailySpend.toFixed(2)}`;
    fillEl.style.width = `${Math.min(dailyPercent, 100)}%`;
    
    // Update status classes
    widget.classList.remove('warning', 'exceeded');
    if (data.status === 'exceeded') {
        widget.classList.add('exceeded');
    } else if (data.status === 'warning') {
        widget.classList.add('warning');
    }
    
    // Click handler to go to settings
    widget.onclick = () => navigateTo('settings');
}

function updateBudgetSettings(data) {
    const config = data.config || {};
    const spend = data.spend || {};
    
    // Update form fields
    const dailyLimitInput = document.getElementById('dailyLimit');
    const weeklyLimitInput = document.getElementById('weeklyLimit');
    const monthlyLimitInput = document.getElementById('monthlyLimit');
    const alertThresholdInput = document.getElementById('alertThreshold');
    const hardLimitInput = document.getElementById('hardLimit');
    
    if (dailyLimitInput) dailyLimitInput.value = config.daily_limit || 10;
    if (weeklyLimitInput) weeklyLimitInput.value = config.weekly_limit || 50;
    if (monthlyLimitInput) monthlyLimitInput.value = config.monthly_limit || 100;
    if (alertThresholdInput) {
        alertThresholdInput.value = (config.alert_threshold || 0.8) * 100;
        document.getElementById('alertThresholdValue').textContent = `${Math.round((config.alert_threshold || 0.8) * 100)}%`;
    }
    if (hardLimitInput) hardLimitInput.checked = config.hard_limit || false;
    
    // Update enforcement badge
    const enforcementBadge = document.getElementById('budgetEnforcement');
    if (enforcementBadge) {
        enforcementBadge.textContent = config.hard_limit ? 'Hard Limit' : 'Advisory';
        enforcementBadge.style.background = config.hard_limit ? 'rgba(239, 68, 68, 0.15)' : 'rgba(59, 130, 246, 0.15)';
        enforcementBadge.style.color = config.hard_limit ? 'var(--accent-red)' : 'var(--accent-blue)';
    }
    
    // Update spending cards
    updateSpendingCard('daily', spend.daily_spend, config.daily_limit, spend.daily_percent, data.status);
    updateSpendingCard('weekly', spend.weekly_spend, config.weekly_limit, spend.weekly_percent, data.status);
    updateSpendingCard('monthly', spend.monthly_spend, config.monthly_limit, spend.monthly_percent, data.status);
    
    // Update alert
    const alertEl = document.getElementById('spendingAlert');
    const alertTextEl = document.getElementById('spendingAlertText');
    if (alertEl) {
        if (data.status === 'warning' || data.status === 'exceeded') {
            alertEl.style.display = 'flex';
            alertTextEl.textContent = data.status_message;
            alertEl.classList.toggle('exceeded', data.status === 'exceeded');
        } else {
            alertEl.style.display = 'none';
        }
    }
}

function updateSpendingCard(period, spend, limit, percent, status) {
    const spendEl = document.getElementById(`${period}Spend`);
    const limitEl = document.getElementById(`${period}LimitDisplay`);
    const fillEl = document.getElementById(`${period}Fill`);
    const statusEl = document.getElementById(`${period}Status`);
    
    if (spendEl) spendEl.textContent = `$${(spend || 0).toFixed(2)}`;
    if (limitEl) limitEl.textContent = `$${(limit || 0).toFixed(2)}`;
    if (fillEl) {
        fillEl.style.width = `${Math.min(percent || 0, 100)}%`;
        fillEl.classList.remove('warning', 'exceeded');
        if (percent >= 100) {
            fillEl.classList.add('exceeded');
        } else if (percent >= 80) {
            fillEl.classList.add('warning');
        }
    }
    if (statusEl) {
        statusEl.classList.remove('ok', 'warning', 'exceeded');
        if (percent >= 100) {
            statusEl.textContent = 'EXCEEDED';
            statusEl.classList.add('exceeded');
        } else if (percent >= 80) {
            statusEl.textContent = 'WARNING';
            statusEl.classList.add('warning');
        } else {
            statusEl.textContent = 'OK';
            statusEl.classList.add('ok');
        }
    }
}

async function saveBudgetSettings() {
    const dailyLimit = parseFloat(document.getElementById('dailyLimit').value) || 0;
    const weeklyLimit = parseFloat(document.getElementById('weeklyLimit').value) || 0;
    const monthlyLimit = parseFloat(document.getElementById('monthlyLimit').value) || 0;
    const alertThreshold = (parseFloat(document.getElementById('alertThreshold').value) || 80) / 100;
    const hardLimit = document.getElementById('hardLimit').checked;
    
    if (DEMO_MODE) {
        showNotification('Budget settings updated (demo mode)', 'success');
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/v1/budget`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                daily_limit: dailyLimit,
                weekly_limit: weeklyLimit,
                monthly_limit: monthlyLimit,
                alert_threshold: alertThreshold,
                hard_limit: hardLimit
            })
        });
        
        if (response.ok) {
            showNotification('Budget settings saved successfully!', 'success');
            loadBudgetStatus();
        } else {
            showNotification('Failed to save budget settings', 'error');
        }
    } catch (error) {
        console.error('Error saving budget:', error);
        showNotification('Error saving budget settings', 'error');
    }
}

async function loadSettings() {
    await loadBudgetStatus();
}

// Initialize settings page event listeners
document.addEventListener('DOMContentLoaded', () => {
    // Settings page elements
    const settingsPage = document.getElementById('settingsPage');
    if (settingsPage) {
        elements.pages.settings = settingsPage;
    }
    
    // Save budget button
    const saveBudgetBtn = document.getElementById('saveBudgetBtn');
    if (saveBudgetBtn) {
        saveBudgetBtn.addEventListener('click', saveBudgetSettings);
    }
    
    // Refresh budget button
    const refreshBudgetBtn = document.getElementById('refreshBudgetBtn');
    if (refreshBudgetBtn) {
        refreshBudgetBtn.addEventListener('click', () => {
            loadBudgetStatus();
            showToast('Budget data refreshed');
        });
    }
    
    // Alert threshold slider
    const alertThreshold = document.getElementById('alertThreshold');
    if (alertThreshold) {
        alertThreshold.addEventListener('input', (e) => {
            document.getElementById('alertThresholdValue').textContent = `${e.target.value}%`;
        });
    }
    
    // Budget widget click
    const budgetWidget = document.getElementById('budgetWidget');
    if (budgetWidget) {
        budgetWidget.addEventListener('click', () => navigateTo('settings'));
    }
    
    // Load budget status on page load
    loadBudgetStatus();
});

// Update navigation to include settings
const originalNavigateTo = navigateTo;
navigateTo = function(page) {
    // Update nav
    elements.navItems.forEach(item => {
        item.classList.toggle('active', item.dataset.page === page);
    });
    
    // Update pages
    Object.entries(elements.pages).forEach(([key, el]) => {
        if (el) el.classList.toggle('hidden', key !== page);
    });
    
    // Update title
    const titles = {
        dashboard: 'Dashboard',
        models: 'Models',
        routing: 'Routing',
        analytics: 'Analytics',
        playground: 'Playground',
        'local-models': 'Local Models',
        settings: 'Settings',
    };
    elements.pageTitle.textContent = titles[page] || page;
    
    state.currentPage = page;
    
    // Load page data
    if (page === 'models') loadModels();
    if (page === 'routing') loadRouting();
    if (page === 'analytics') loadAnalytics();
    if (page === 'local-models') loadLocalModels();
    if (page === 'settings') loadSettings();
};

// --- Local Models Functions ---

async function loadLocalModels() {
    const statusIcon = document.getElementById('ollamaStatusIcon');
    const statusTitle = document.getElementById('ollamaStatusTitle');
    const statusMessage = document.getElementById('ollamaStatusMessage');
    const modelsGrid = document.getElementById('localModelsGrid');
    const emptyState = document.getElementById('localModelsEmpty');
    
    try {
        // First check status
        const statusData = await fetchAPI('/v1/local-models/status');
        
        if (statusData?.available) {
            statusIcon?.classList.remove('offline');
            statusIcon?.classList.add('available');
            statusTitle.textContent = 'Ollama Running';
            statusMessage.textContent = `Connected to ${statusData.host}`;
        } else {
            statusIcon?.classList.remove('available');
            statusIcon?.classList.add('offline');
            statusTitle.textContent = 'Ollama Offline';
            statusMessage.textContent = statusData?.message || 'Start Ollama to use local models';
            emptyState.style.display = 'block';
            return;
        }
        
        // Fetch models
        const data = await fetchAPI('/v1/local-models');
        
        if (!data || !data.models || data.models.length === 0) {
            emptyState.style.display = 'block';
            return;
        }
        
        emptyState.style.display = 'none';
        
        // Render model cards
        const existingCards = modelsGrid.querySelectorAll('.local-model-card');
        existingCards.forEach(card => card.remove());
        
        data.models.forEach(model => {
            const card = renderLocalModelCard(model);
            modelsGrid.insertBefore(card, emptyState);
        });
        
    } catch (error) {
        console.error('Error loading local models:', error);
        statusIcon?.classList.remove('available');
        statusIcon?.classList.add('offline');
        statusTitle.textContent = 'Connection Error';
        statusMessage.textContent = 'Could not connect to API';
    }
}

function renderLocalModelCard(model) {
    const card = document.createElement('div');
    card.className = 'panel local-model-card';
    
    card.innerHTML = `
        <div class="model-header">
            <span class="model-name">${model.display_name || model.name}</span>
            <span class="tag-local">LOCAL</span>
            <span class="tag-free">FREE</span>
        </div>
        <div class="model-meta">
            ${model.family ? `<span>Family: ${model.family}</span>` : ''}
            ${model.parameter_size ? `<span>Size: ${model.parameter_size}</span>` : ''}
            ${model.quantization ? `<span>Quant: ${model.quantization}</span>` : ''}
            <span>${model.size_gb?.toFixed(1) || '?'} GB</span>
        </div>
        <div class="model-actions">
            <button class="btn btn-sm btn-primary" onclick="testLocalModel('${model.name}')">
                Test
            </button>
        </div>
    `;
    
    return card;
}

async function testLocalModel(modelName) {
    try {
        const response = await fetchAPI('/v1/local-models/chat', {
            method: 'POST',
            body: JSON.stringify({
                model: modelName,
                messages: [{ role: 'user', content: 'Say hello in one sentence.' }],
                temperature: 0.7
            })
        });
        
        if (response?.message?.content) {
            alert(`Response from ${modelName}:\n\n${response.message.content}`);
        } else {
            alert('No response received');
        }
    } catch (error) {
        alert(`Error testing model: ${error.message}`);
    }
}

// Event listeners for Local Models page
document.getElementById('refreshLocalModelsBtn')?.addEventListener('click', () => {
    loadLocalModels();
});

// Popular model buttons
document.querySelectorAll('.popular-model-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const modelName = btn.dataset.model;
        alert(`To install ${modelName}, run:\n\nollama pull ${modelName}`);
    });
});
