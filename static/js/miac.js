/**
 * MIAC — Módulo Integrado de Arquivos e Controle
 * Global JavaScript Library
 * All shared utilities, UI helpers, and feature enhancements.
 */

'use strict';

const MIAC = (function () {

    /* ═══════════════════════════════════════
       TOAST NOTIFICATION SYSTEM
    ═══════════════════════════════════════ */
    let toastContainer = null;

    function _ensureToastContainer() {
        if (!toastContainer) {
            toastContainer = document.createElement('div');
            toastContainer.className = 'toast-container position-fixed bottom-0 end-0 p-3';
            toastContainer.style.zIndex = '9999';
            document.body.appendChild(toastContainer);
        }
    }

    /**
     * Show a toast notification.
     * @param {string} message
     * @param {'success'|'danger'|'warning'|'info'} type
     * @param {number} duration  ms before auto-dismiss (default 4000)
     */
    function toast(message, type = 'success', duration = 4000) {
        _ensureToastContainer();
        const icons = {
            success: 'fa-check-circle',
            danger: 'fa-times-circle',
            warning: 'fa-exclamation-triangle',
            info: 'fa-info-circle',
        };
        const el = document.createElement('div');
        el.className = `toast align-items-center text-white bg-${type} border-0 show`;
        el.setAttribute('role', 'alert');
        el.innerHTML = `
            <div class="d-flex">
                <div class="toast-body d-flex align-items-center gap-2">
                    <i class="fas ${icons[type] || 'fa-bell'}"></i>
                    <span>${message}</span>
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto"
                        data-bs-dismiss="toast" aria-label="Fechar"></button>
            </div>`;
        toastContainer.appendChild(el);
        const bsToast = new bootstrap.Toast(el, { delay: duration });
        bsToast.show();
        el.addEventListener('hidden.bs.toast', () => el.remove());
    }

    /* ═══════════════════════════════════════
       STYLED CONFIRM DIALOG
    ═══════════════════════════════════════ */
    let _confirmResolve = null;

    function _ensureConfirmModal() {
        if (document.getElementById('miac-confirm-modal')) return;
        const m = document.createElement('div');
        m.id = 'miac-confirm-modal';
        m.className = 'modal fade';
        m.tabIndex = -1;
        m.setAttribute('aria-hidden', 'true');
        m.innerHTML = `
            <div class="modal-dialog modal-dialog-centered modal-sm">
                <div class="modal-content border-0 shadow">
                    <div class="modal-header border-0 pb-0">
                        <h6 class="modal-title fw-600" id="miac-confirm-title">Confirmar</h6>
                    </div>
                    <div class="modal-body pt-2">
                        <p id="miac-confirm-msg" class="mb-0 text-muted" style="font-size:.9rem;"></p>
                    </div>
                    <div class="modal-footer border-0 pt-0 gap-2">
                        <button id="miac-confirm-cancel" class="btn btn-sm btn-outline-secondary">Cancelar</button>
                        <button id="miac-confirm-ok" class="btn btn-sm btn-danger">Confirmar</button>
                    </div>
                </div>
            </div>`;
        document.body.appendChild(m);
        document.getElementById('miac-confirm-cancel').addEventListener('click', () => {
            bootstrap.Modal.getInstance(m).hide();
            if (_confirmResolve) { _confirmResolve(false); _confirmResolve = null; }
        });
        document.getElementById('miac-confirm-ok').addEventListener('click', () => {
            bootstrap.Modal.getInstance(m).hide();
            if (_confirmResolve) { _confirmResolve(true); _confirmResolve = null; }
        });
        m.addEventListener('hidden.bs.modal', () => {
            if (_confirmResolve) { _confirmResolve(false); _confirmResolve = null; }
        });
    }

    /**
     * Show a styled confirm dialog. Returns a Promise<boolean>.
     * @param {string} message
     * @param {string} title
     * @param {string} okLabel
     * @param {'danger'|'primary'|'warning'} okType
     */
    function confirm(message, title = 'Confirmar', okLabel = 'Confirmar', okType = 'danger') {
        _ensureConfirmModal();
        const m = document.getElementById('miac-confirm-modal');
        document.getElementById('miac-confirm-title').textContent = title;
        document.getElementById('miac-confirm-msg').textContent = message;
        const okBtn = document.getElementById('miac-confirm-ok');
        okBtn.textContent = okLabel;
        okBtn.className = `btn btn-sm btn-${okType}`;
        const modal = new bootstrap.Modal(m);
        modal.show();
        return new Promise(resolve => { _confirmResolve = resolve; });
    }

    /* ═══════════════════════════════════════
       FETCH WRAPPER WITH ERROR HANDLING
    ═══════════════════════════════════════ */

    /**
     * Wrapper around fetch() with automatic JSON handling and error toasts.
     * @param {string} url
     * @param {object} options  - standard fetch options, plus `silent: true` to suppress toasts
     * @returns {Promise<any>}  - resolves with JSON body or null
     */
    async function api(url, options = {}) {
        const { silent = false, ...fetchOpts } = options;
        try {
            const resp = await fetch(url, {
                headers: { 'X-Requested-With': 'XMLHttpRequest', ...(fetchOpts.headers || {}) },
                ...fetchOpts,
            });
            const contentType = resp.headers.get('content-type') || '';
            const body = contentType.includes('application/json') ? await resp.json() : await resp.text();
            if (!resp.ok) {
                const msg = (typeof body === 'object' && body.error) ? body.error
                    : `Erro ${resp.status}: ${resp.statusText}`;
                if (!silent) toast(msg, 'danger');
                return null;
            }
            return body;
        } catch (err) {
            if (!silent) toast('Erro de comunicação com o servidor.', 'danger');
            return null;
        }
    }

    /* ═══════════════════════════════════════
       LOADING STATE HELPER
    ═══════════════════════════════════════ */

    /**
     * Show or hide a loading spinner inside any element.
     * @param {string|HTMLElement} target  - CSS selector or element
     * @param {boolean} state
     * @param {string} message
     */
    function loading(target, state, message = 'Carregando...') {
        const el = typeof target === 'string' ? document.querySelector(target) : target;
        if (!el) return;
        if (state) {
            el.dataset.miacOriginal = el.innerHTML;
            el.innerHTML = `<div class="text-center py-4">
                <div class="spinner-border text-primary" role="status" style="width:1.8rem;height:1.8rem;"></div>
                <p class="text-muted mt-2 mb-0" style="font-size:.85rem;">${message}</p>
            </div>`;
        } else if (el.dataset.miacOriginal !== undefined) {
            el.innerHTML = el.dataset.miacOriginal;
            delete el.dataset.miacOriginal;
        }
    }

    /**
     * Disable a button and show a spinner inside it.
     * @param {HTMLElement} btn
     * @param {boolean} state
     * @param {string} label - label to show while loading
     */
    function btnLoading(btn, state, label = '') {
        if (state) {
            btn.dataset.miacLabel = btn.innerHTML;
            btn.disabled = true;
            btn.innerHTML = `<span class="spinner-border spinner-border-sm me-1" role="status"></span>${label}`;
        } else {
            btn.disabled = false;
            if (btn.dataset.miacLabel !== undefined) {
                btn.innerHTML = btn.dataset.miacLabel;
                delete btn.dataset.miacLabel;
            }
        }
    }

    /* ═══════════════════════════════════════
       TEXT UTILITIES
    ═══════════════════════════════════════ */

    /** Remove diacritics/accents and lowercase. */
    function normalizeText(text) {
        return String(text || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
    }

    /** Format a dd/mm/yyyy string to yyyy-mm-dd for <input type="date">. */
    function toInputDate(dateStr) {
        if (!dateStr) return '';
        const parts = String(dateStr).split('/');
        if (parts.length === 3) return `${parts[2]}-${parts[1]}-${parts[0]}`;
        return dateStr;
    }

    /** Format a yyyy-mm-dd string to dd/mm/yyyy for display. */
    function toDisplayDate(dateStr) {
        if (!dateStr) return '';
        const parts = String(dateStr).split('-');
        if (parts.length === 3) return `${parts[2]}/${parts[1]}/${parts[0]}`;
        return dateStr;
    }

    /**
     * Return a debounced version of fn.
     * @param {Function} fn
     * @param {number} ms
     */
    function debounce(fn, ms = 350) {
        let timer;
        return function (...args) {
            clearTimeout(timer);
            timer = setTimeout(() => fn.apply(this, args), ms);
        };
    }

    /**
     * Throttle fn to at most once per ms.
     */
    function throttle(fn, ms = 200) {
        let last = 0;
        return function (...args) {
            const now = Date.now();
            if (now - last >= ms) { last = now; fn.apply(this, args); }
        };
    }

    /* ═══════════════════════════════════════
       COPY TO CLIPBOARD
    ═══════════════════════════════════════ */

    /**
     * Copy text to clipboard and show a toast.
     */
    async function copyToClipboard(text) {
        try {
            await navigator.clipboard.writeText(text);
            toast('Copiado para a área de transferência!', 'success', 2500);
        } catch {
            toast('Não foi possível copiar.', 'warning');
        }
    }

    /* ═══════════════════════════════════════
       SIDEBAR TOGGLE (global)
    ═══════════════════════════════════════ */

    function toggleSidebar() {
        const sidebar = document.getElementById('sidebar');
        const overlay = document.querySelector('.sidebar-overlay');
        if (sidebar) sidebar.classList.toggle('open');
        if (overlay) overlay.classList.toggle('active');
    }

    /* ═══════════════════════════════════════
       BACK TO TOP BUTTON (auto-init)
    ═══════════════════════════════════════ */

    function _initBackToTop() {
        const btn = document.createElement('button');
        btn.id = 'miac-back-top';
        btn.title = 'Voltar ao topo';
        btn.setAttribute('aria-label', 'Voltar ao topo');
        btn.innerHTML = '<i class="fas fa-arrow-up"></i>';
        Object.assign(btn.style, {
            display: 'none', position: 'fixed', bottom: '24px', right: '24px',
            zIndex: '9990', width: '42px', height: '42px', borderRadius: '50%',
            border: 'none', background: 'linear-gradient(135deg,#2c3e50,#3498db)',
            color: '#fff', boxShadow: '0 4px 14px rgba(0,0,0,.3)',
            cursor: 'pointer', fontSize: '1rem', transition: 'opacity .2s, transform .2s',
        });
        document.body.appendChild(btn);
        btn.addEventListener('click', () => window.scrollTo({ top: 0, behavior: 'smooth' }));
        btn.addEventListener('mouseenter', () => { btn.style.transform = 'scale(1.12)'; });
        btn.addEventListener('mouseleave', () => { btn.style.transform = 'scale(1)'; });
        const handler = throttle(() => {
            btn.style.display = window.scrollY > 320 ? 'flex' : 'none';
            if (btn.style.display === 'flex') {
                btn.style.alignItems = 'center';
                btn.style.justifyContent = 'center';
            }
        }, 100);
        window.addEventListener('scroll', handler, { passive: true });
    }

    /* ═══════════════════════════════════════
       KEYBOARD SHORTCUT SYSTEM
    ═══════════════════════════════════════ */

    const _shortcuts = {};

    /**
     * Register a keyboard shortcut.
     * @param {string} key  - key value (e.g. '/', 'Escape', 's')
     * @param {Function} fn
     * @param {object} opts - { ctrl, shift, alt, description }
     */
    function registerShortcut(key, fn, opts = {}) {
        _shortcuts[key] = { fn, ...opts };
    }

    function _initKeyboard() {
        document.addEventListener('keydown', function (e) {
            const tag = document.activeElement.tagName;
            const editing = tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT'
                || document.activeElement.isContentEditable;

            // Global: Escape closes modals
            if (e.key === 'Escape') {
                const openModal = document.querySelector('.modal.show');
                if (openModal) bootstrap.Modal.getInstance(openModal)?.hide();
            }

            // '/' → focus search (if not typing)
            if (e.key === '/' && !editing) {
                const searchInput = document.getElementById('nome') || document.querySelector('input[type="search"], input[name="nome"]');
                if (searchInput) { e.preventDefault(); searchInput.focus(); }
            }

            // Custom shortcuts
            for (const [k, s] of Object.entries(_shortcuts)) {
                if (e.key === k
                    && (!s.ctrl || e.ctrlKey)
                    && (!s.shift || e.shiftKey)
                    && (!s.alt || e.altKey)
                    && (!editing || s.allowEditing)) {
                    e.preventDefault();
                    s.fn(e);
                }
            }
        });
    }

    /* ═══════════════════════════════════════
       ONLINE / OFFLINE STATUS BANNER
    ═══════════════════════════════════════ */

    function _initOfflineBanner() {
        let banner = null;
        function show() {
            if (banner) return;
            banner = document.createElement('div');
            banner.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:99999;background:#e74c3c;color:#fff;text-align:center;padding:8px;font-size:.85rem;';
            banner.innerHTML = '<i class="fas fa-wifi me-2"></i>Sem conexão com a internet — algumas funções podem não funcionar.';
            document.body.prepend(banner);
        }
        function hide() {
            if (banner) { banner.remove(); banner = null; }
        }
        if (!navigator.onLine) show();
        window.addEventListener('offline', show);
        window.addEventListener('online', () => { hide(); toast('Conexão restaurada!', 'success', 2500); });
    }

    /* ═══════════════════════════════════════
       FLASH MESSAGE AUTO-DISMISS
    ═══════════════════════════════════════ */

    function _initFlashMessages() {
        document.querySelectorAll('.flash-message').forEach(el => {
            setTimeout(() => {
                el.style.transition = 'opacity .4s, transform .4s';
                el.style.opacity = '0';
                el.style.transform = 'translateX(120%)';
                setTimeout(() => el.remove(), 420);
            }, 5000);
            el.style.cursor = 'pointer';
            el.addEventListener('click', () => el.remove());
        });
    }

    /* ═══════════════════════════════════════
       CONFIRM-DELETE PATTERN (data-confirm-delete)
    ═══════════════════════════════════════ */

    function _initConfirmDelete() {
        document.addEventListener('submit', async function (e) {
            const form = e.target;
            const msg = form.dataset.confirmDelete;
            if (!msg) return;
            e.preventDefault();
            const ok = await confirm(msg, 'Confirmar exclusão', 'Excluir', 'danger');
            if (ok) form.submit();
        });
        document.addEventListener('click', async function (e) {
            const btn = e.target.closest('[data-confirm-delete]');
            if (!btn || btn.tagName === 'FORM') return;
            e.preventDefault();
            const msg = btn.dataset.confirmDelete;
            const ok = await confirm(msg || 'Confirmar exclusão?', 'Confirmar exclusão', 'Excluir', 'danger');
            if (!ok) return;
            const href = btn.href || btn.dataset.href;
            if (href) window.location.href = href;
        });
    }

    /* ═══════════════════════════════════════
       COPY BUTTONS (data-copy)
    ═══════════════════════════════════════ */

    function _initCopyButtons() {
        document.addEventListener('click', function (e) {
            const btn = e.target.closest('[data-copy]');
            if (!btn) return;
            copyToClipboard(btn.dataset.copy);
        });
    }

    /* ═══════════════════════════════════════
       AUTO-UPPERCASE (data-uppercase)
    ═══════════════════════════════════════ */

    function _initAutoUppercase() {
        document.addEventListener('input', function (e) {
            if (e.target.dataset.uppercase !== undefined) {
                const pos = e.target.selectionStart;
                e.target.value = e.target.value.toUpperCase();
                e.target.setSelectionRange(pos, pos);
            }
        });
    }

    /* ═══════════════════════════════════════
       CHARACTER COUNTER (data-maxlength-counter)
    ═══════════════════════════════════════ */

    function _initCharCounters() {
        document.querySelectorAll('[data-maxlength-counter]').forEach(input => {
            const max = input.maxLength;
            if (max <= 0) return;
            const counter = document.createElement('small');
            counter.className = 'form-text text-muted text-end d-block';
            const update = () => {
                const remaining = max - input.value.length;
                counter.textContent = `${remaining} caractere${remaining !== 1 ? 's' : ''} restante${remaining !== 1 ? 's' : ''}`;
                counter.className = `form-text text-end d-block ${remaining < 20 ? 'text-danger' : 'text-muted'}`;
            };
            input.after(counter);
            input.addEventListener('input', update);
            update();
        });
    }

    /* ═══════════════════════════════════════
       SMOOTH PAGE TRANSITION
    ═══════════════════════════════════════ */

    function _initPageTransition() {
        document.body.style.opacity = '0';
        document.body.style.transition = 'opacity .25s ease';
        requestAnimationFrame(() => { document.body.style.opacity = '1'; });
        document.addEventListener('click', function (e) {
            const a = e.target.closest('a[href]');
            if (!a) return;
            const href = a.getAttribute('href');
            if (!href || href.startsWith('#') || href.startsWith('javascript')
                || a.target === '_blank' || e.ctrlKey || e.metaKey) return;
            e.preventDefault();
            document.body.style.opacity = '0';
            setTimeout(() => { window.location.href = href; }, 230);
        });
    }

    /* ═══════════════════════════════════════
       STATUS BADGE RENDERER
    ═══════════════════════════════════════ */

    /**
     * Return HTML for a status badge.
     * @param {'Atualizado'|'Vencido'|string} status
     */
    function statusBadge(status) {
        if (!status) return '<span class="status-badge status-unknown">—</span>';
        const s = status.toLowerCase();
        if (s.includes('atualiz')) return `<span class="status-badge status-ok"><i class="fas fa-check-circle"></i>${status}</span>`;
        if (s.includes('vencid') || s.includes('desatualiz')) return `<span class="status-badge status-expired"><i class="fas fa-times-circle"></i>${status}</span>`;
        return `<span class="status-badge status-unknown">${status}</span>`;
    }

    /* ═══════════════════════════════════════
       RELATIVE TIME
    ═══════════════════════════════════════ */

    /**
     * Return a human-readable relative time string from a date.
     * @param {string|Date} date
     */
    function relativeTime(date) {
        const d = date instanceof Date ? date : new Date(date);
        if (isNaN(d)) return '';
        const diff = Date.now() - d.getTime();
        const abs = Math.abs(diff);
        const future = diff < 0;
        const mins  = Math.floor(abs / 60000);
        const hours = Math.floor(abs / 3600000);
        const days  = Math.floor(abs / 86400000);
        let label;
        if (mins < 1)        label = 'agora mesmo';
        else if (mins < 60)  label = `${mins} min`;
        else if (hours < 24) label = `${hours}h`;
        else if (days < 30)  label = `${days} dia${days > 1 ? 's' : ''}`;
        else {
            const months = Math.floor(days / 30);
            label = `${months} mês${months > 1 ? 'es' : ''}`;
        }
        return future ? `em ${label}` : `há ${label}`;
    }

    /* ═══════════════════════════════════════
       RESTORE VERSAO HELPER (shared)
    ═══════════════════════════════════════ */

    /**
     * Restore a document version via POST and reload on success.
     * @param {number} docId
     * @param {number} versao
     */
    async function restaurarVersao(docId, versao) {
        const ok = await confirm(
            `Restaurar para a versão ${versao}? A versão atual será arquivada.`,
            'Restaurar versão', 'Restaurar', 'primary'
        );
        if (!ok) return;
        const data = await api(`/miac/restaurar_versao/${docId}/${versao}`, { method: 'POST' });
        if (data && data.success) {
            toast(data.message || 'Versão restaurada com sucesso!', 'success');
            setTimeout(() => location.reload(), 1200);
        }
    }

    /* ═══════════════════════════════════════
       INIT (called on DOMContentLoaded)
    ═══════════════════════════════════════ */

    function init() {
        _initBackToTop();
        _initKeyboard();
        _initOfflineBanner();
        _initFlashMessages();
        _initConfirmDelete();
        _initCopyButtons();
        _initAutoUppercase();
        _initCharCounters();
        _initPageTransition();
    }

    /* ═══════════════════════════════════════
       PUBLIC API
    ═══════════════════════════════════════ */
    return {
        toast,
        confirm,
        api,
        loading,
        btnLoading,
        normalizeText,
        toInputDate,
        toDisplayDate,
        debounce,
        throttle,
        copyToClipboard,
        toggleSidebar,
        registerShortcut,
        statusBadge,
        relativeTime,
        restaurarVersao,
        init,
    };
})();

// Auto-initialize on DOM ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', MIAC.init);
} else {
    MIAC.init();
}

// Expose toggleSidebar globally for onclick= attributes
window.toggleSidebar = MIAC.toggleSidebar;
