class KeywordChipInput {
    constructor(inputElement, hiddenInputElement) {
        this.input = inputElement;
        this.hiddenInput = hiddenInputElement;
        this.chips = [];
        this.chipContainer = inputElement.parentElement;
        this.init();
    }

    init() {
        // Load existing keywords from hidden input
        this.loadFromHiddenInput();
        
        // Event listeners
        this.input.addEventListener('keydown', this.handleKeyDown.bind(this));
        this.input.addEventListener('blur', this.handleBlur.bind(this));
        this.input.addEventListener('paste', this.handlePaste.bind(this));
        
        // Render initial chips
        this.renderChips();
    }

    loadFromHiddenInput() {
        const value = this.hiddenInput.value || '';
        if (value.trim()) {
            this.chips = value.split(',').map(k => k.trim()).filter(k => k);
        }
    }

    handleKeyDown(e) {
        // Create chip on comma or Enter
        if (e.key === ',' || e.key === 'Enter') {
            e.preventDefault();
            this.addChip(this.input.value.trim());
        }
        // Remove last chip on Backspace if input is empty
        else if (e.key === 'Backspace' && this.input.value === '' && this.chips.length > 0) {
            this.removeChip(this.chips.length - 1);
        }
    }

    handleBlur() {
        // Add any remaining text as a chip when input loses focus
        if (this.input.value.trim()) {
            this.addChip(this.input.value.trim());
        }
    }

    handlePaste(e) {
        // Allow paste, then process after a short delay
        setTimeout(() => {
            const value = this.input.value;
            if (value.includes(',')) {
                const keywords = value.split(',').map(k => k.trim()).filter(k => k);
                this.input.value = '';
                keywords.forEach(keyword => this.addChip(keyword));
            }
        }, 10);
    }

    addChip(keyword) {
        if (!keyword) return;
        
        // Prevent duplicates
        if (this.chips.includes(keyword)) {
            this.input.value = '';
            return;
        }
        
        this.chips.push(keyword);
        this.input.value = '';
        this.renderChips();
        this.updateHiddenInput();
    }

    removeChip(index) {
        if (index >= 0 && index < this.chips.length) {
        this.chips.splice(index, 1);
        this.renderChips();
        this.updateHiddenInput();
        this.input.focus();
        }
    }

    removeChipByKeyword(keyword) {
        const index = this.chips.indexOf(keyword);
        if (index !== -1) {
            this.removeChip(index);
        }
    }

    renderChips() {
        // Remove existing chips (but keep the input)
        const existingChips = this.chipContainer.querySelectorAll('.keyword-chip');
        existingChips.forEach(chip => chip.remove());
        
        // Add chips before the input
        this.chips.forEach((keyword, index) => {
            const chip = document.createElement('span');
            chip.className = 'keyword-chip badge bg-secondary d-inline-flex align-items-center gap-1 me-1';
            chip.innerHTML = `
                <span>${this.escapeHtml(keyword)}</span>
                <button type="button" 
                        class="btn-close btn-close-white" 
                        style="font-size: 0.65em;"
                        aria-label="Remove ${this.escapeHtml(keyword)}"
                        data-keyword="${this.escapeHtml(keyword)}"></button>
            `;
            
            // Add remove handler - use keyword instead of index to avoid index issues
            const removeBtn = chip.querySelector('.btn-close');
            removeBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                const keywordToRemove = removeBtn.getAttribute('data-keyword');
                this.removeChipByKeyword(keywordToRemove);
            });
            
            // Insert before input
            this.chipContainer.insertBefore(chip, this.input);
        });
    }

    updateHiddenInput() {
        this.hiddenInput.value = this.chips.join(',');
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    getKeywords() {
        return this.chips;
    }

    clear() {
        this.chips = [];
        this.input.value = '';
        this.renderChips();
        this.updateHiddenInput();
    }
}

/**
 * Reusable initializer for KeywordChipInput components
 * Handles initialization across multiple pages with different container contexts
 */
class KeywordChipInputInitializer {
    /**
     * Initialize keyword chip input for a given container
     * @param {HTMLElement|string} container - Container element or selector to search within
     * @param {Object} options - Configuration options
     * @param {boolean} options.allowMultiple - Allow multiple instances (default: false)
     * @param {string} options.wrapperSelector - Custom selector for keyword wrapper (default: '.keyword-chips-wrapper')
     * @param {string} options.inputSelector - Custom selector for input (default: '.keyword-input, input[type="text"]')
     * @param {string} options.hiddenInputId - Custom ID for hidden input (default: 'keywords-hidden')
     * @returns {KeywordChipInput|null} Initialized KeywordChipInput instance or null
     */
    static initialize(container = document, options = {}) {
        const {
            allowMultiple = false,
            wrapperSelector = '.keyword-chips-wrapper',
            inputSelector = '.keyword-input, input[type="text"]',
            hiddenInputId = 'keywords-hidden'
        } = options;

        // Get container element
        const containerEl = typeof container === 'string' 
            ? document.querySelector(container) 
            : container;

        if (!containerEl) {
            console.warn('KeywordChipInputInitializer: Container not found');
            return null;
        }

        // Check if KeywordChipInput class is available
        if (typeof KeywordChipInput === 'undefined') {
            console.warn('KeywordChipInputInitializer: KeywordChipInput class not loaded');
            return null;
        }

        // Find the keyword wrapper
        const keywordsWrapper = containerEl.querySelector(wrapperSelector);
        if (!keywordsWrapper) {
            return null; // No keyword input on this page, silently return
        }

        // Find the input and hidden input
        const keywordsInput = keywordsWrapper.querySelector(inputSelector);
        const keywordsHidden = document.getElementById(hiddenInputId);

        if (!keywordsInput || !keywordsHidden) {
            console.warn('KeywordChipInputInitializer: Required elements not found');
            return null;
        }

        // Check if already initialized (unless multiple instances allowed)
        if (!allowMultiple && window.keywordChipInput) {
            return window.keywordChipInput;
        }

        // Ensure the input has the right classes and styles
        keywordsInput.classList.add('keyword-input', 'border-0', 'flex-grow-1');
        if (!keywordsInput.style.minWidth) {
            keywordsInput.style.minWidth = '120px';
        }
        if (!keywordsInput.style.outline) {
            keywordsInput.style.outline = 'none';
        }
        if (!keywordsInput.placeholder) {
            keywordsInput.placeholder = 'Type keywords and press comma';
        }

        // Initialize chip input
        const chipInput = new KeywordChipInput(keywordsInput, keywordsHidden);
        
        // Store globally if not allowing multiple instances
        if (!allowMultiple) {
            window.keywordChipInput = chipInput;
        }

        return chipInput;
    }

    /**
     * Initialize keyword chip input when a Bootstrap collapse section is shown
     * @param {HTMLElement|string} collapseElement - Collapse element or selector
     * @param {Object} options - Configuration options (same as initialize)
     * @returns {KeywordChipInput|null} Initialized KeywordChipInput instance or null
     */
    static initializeOnCollapseShow(collapseElement, options = {}) {
        const collapseEl = typeof collapseElement === 'string'
            ? document.querySelector(collapseElement)
            : collapseElement;

        if (!collapseEl || !window.bootstrap) {
            return null;
        }

        // Initialize immediately if collapse is already shown
        if (collapseEl.classList.contains('show')) {
            return this.initialize(collapseEl, options);
        }

        // Otherwise, wait for the collapse to be shown
        collapseEl.addEventListener('shown.bs.collapse', function() {
            KeywordChipInputInitializer.initialize(collapseEl, options);
        });

        return null;
    }

    /**
     * Auto-initialize on DOMContentLoaded
     * Looks for keyword chip inputs in the document and initializes them
     * @param {Object} options - Configuration options (same as initialize)
     */
    static autoInitialize(options = {}) {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => {
                this.initialize(document, options);
            });
        } else {
            // DOM already loaded
            this.initialize(document, options);
        }
    }
}

// Export for use in other scripts
if (typeof window !== "undefined") {
	window.KeywordChipInput = KeywordChipInput;
    window.KeywordChipInputInitializer = KeywordChipInputInitializer;
}