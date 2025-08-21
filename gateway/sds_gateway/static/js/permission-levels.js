/**
 * Permission Levels JavaScript
 * Handles permission level selection and display functionality
 */

document.addEventListener('DOMContentLoaded', function() {
    initializePermissionLevels();
});

function initializePermissionLevels() {
    // Initialize permission level selectors
    const permissionSelects = document.querySelectorAll('[id^="permission-level-"]');
    
    permissionSelects.forEach(select => {
        // Add change event listener
        select.addEventListener('change', handlePermissionLevelChange);
        
        // Add visual feedback on selection
        select.addEventListener('focus', function() {
            this.parentElement.classList.add('focused');
        });
        
        select.addEventListener('blur', function() {
            this.parentElement.classList.remove('focused');
        });
    });

    // Initialize permission badges with tooltips
    initializePermissionBadges();
}

function handlePermissionLevelChange(event) {
    const select = event.target;
    const selectedValue = select.value;
    const form = select.closest('form');
    const saveButton = form.querySelector('[id^="share-item-btn-"]');
    const pendingMessage = form.querySelector('[id^="pending-changes-message-"]');
    
    // Update visual feedback
    updatePermissionLevelVisualFeedback(select, selectedValue);
    
    // Update form data
    updateFormPermissionLevel(form, selectedValue);
    
    // Show pending changes message
    if (pendingMessage) {
        pendingMessage.classList.remove('d-none');
    }
    
    // Enable save button if there are selected users
    const selectedChips = form.querySelectorAll('.selected-user-chip');
    if (selectedChips.length > 0 && saveButton) {
        saveButton.disabled = false;
    }
    
    // Show permission level description
    showPermissionLevelDescription(select, selectedValue);
}

function updatePermissionLevelVisualFeedback(select, permissionLevel) {
    const section = select.closest('.permission-level-section');
    
    // Remove existing visual classes
    section.classList.remove('viewer-selected', 'contributor-selected', 'co-owner-selected');
    
    // Add new visual class
    section.classList.add(`${permissionLevel}-selected`);
    
    // Update select styling
    select.className = `form-select permission-${permissionLevel}`;
}

function updateFormPermissionLevel(form, permissionLevel) {
    // Remove existing hidden input
    const existingInput = form.querySelector('input[name="permission_level"]');
    if (existingInput) {
        existingInput.remove();
    }
    
    // Create new hidden input
    const hiddenInput = document.createElement('input');
    hiddenInput.type = 'hidden';
    hiddenInput.name = 'permission_level';
    hiddenInput.value = permissionLevel;
    form.appendChild(hiddenInput);
}

function showPermissionLevelDescription(select, permissionLevel) {
    const descriptions = {
        'viewer': 'Can view dataset information and download files',
        'contributor': 'Can add their own assets to the dataset',
        'co-owner': 'Can add/remove assets and edit dataset metadata'
    };
    
    const description = descriptions[permissionLevel];
    if (description) {
        // Create or update description tooltip
        let tooltip = select.parentElement.querySelector('.permission-description-tooltip');
        if (!tooltip) {
            tooltip = document.createElement('div');
            tooltip.className = 'permission-description-tooltip alert alert-info mt-2';
            tooltip.style.fontSize = '0.875rem';
            select.parentElement.appendChild(tooltip);
        }
        
        tooltip.innerHTML = `<i class="bi bi-info-circle me-1"></i>${description}`;
        
        // Auto-hide after 3 seconds
        setTimeout(() => {
            if (tooltip && tooltip.parentElement) {
                tooltip.remove();
            }
        }, 3000);
    }
}

function initializePermissionBadges() {
    const permissionBadges = document.querySelectorAll('.permission-badge');
    
    permissionBadges.forEach(badge => {
        // Add hover tooltip
        const permissionLevel = badge.textContent.trim().toLowerCase().replace(/\s+/g, '-');
        const tooltips = {
            'co-owner': 'Full access: Can add/remove assets and edit dataset metadata',
            'contributor': 'Can add assets: Can add their own assets to the dataset',
            'viewer': 'Read-only: Can view dataset information and download files',
            'owner': 'Dataset owner: Full control over the dataset'
        };
        
        const tooltip = tooltips[permissionLevel];
        if (tooltip) {
            badge.setAttribute('data-bs-toggle', 'tooltip');
            badge.setAttribute('data-bs-placement', 'top');
            badge.setAttribute('title', tooltip);
        }
        
        // Add click animation
        badge.addEventListener('click', function() {
            this.style.transform = 'scale(1.1)';
            setTimeout(() => {
                this.style.transform = '';
            }, 200);
        });
    });
    
    // Initialize Bootstrap tooltips
    if (typeof bootstrap !== 'undefined' && bootstrap.Tooltip) {
        const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
        tooltipTriggerList.map(function (tooltipTriggerEl) {
            return new bootstrap.Tooltip(tooltipTriggerEl);
        });
    }
}

// Export functions for use in other modules
window.PermissionLevels = {
    initialize: initializePermissionLevels,
    handleChange: handlePermissionLevelChange,
    updateVisualFeedback: updatePermissionLevelVisualFeedback,
    showDescription: showPermissionLevelDescription,
    initializeBadges: initializePermissionBadges
}; 