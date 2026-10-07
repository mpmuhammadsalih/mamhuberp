// Universal Dropdown Search Functionality

document.addEventListener('DOMContentLoaded', function() {
    // Initialize search for all select elements
    initializeDropdownSearch();
});

function initializeDropdownSearch() {
    const selects = document.querySelectorAll('select');
    
    selects.forEach(select => {
        // Skip if already has search wrapper
        if (select.parentElement && select.parentElement.classList.contains('dropdown-search-wrapper')) {
            return;
        }

        // Plain select only (no type-to-search)
        if (
            select.hasAttribute('data-no-dropdown-search') ||
            select.classList.contains('no-dropdown-search') ||
            select.id === 'pcMonth' ||
            select.id === 'pcFy' ||
            select.id === 'pcType'
        ) {
            return;
        }
        
        // Only add search if dropdown has more than 5 options
        if (select.options.length <= 5) {
            return;
        }
        
        // Create wrapper
        const wrapper = document.createElement('div');
        wrapper.className = 'dropdown-search-wrapper';
        
        // Create search input container
        const searchContainer = document.createElement('div');
        searchContainer.className = 'dropdown-search-container';
        
        // Create search input
        const searchInput = document.createElement('input');
        searchInput.type = 'text';
        searchInput.className = 'dropdown-search-input';
        searchInput.placeholder = 'Type to search...';
        searchInput.style.display = 'none';
        
        // Create clear button
        const clearBtn = document.createElement('button');
        clearBtn.type = 'button';
        clearBtn.className = 'dropdown-search-clear';
        clearBtn.innerHTML = '×';
        clearBtn.style.display = 'none';
        clearBtn.title = 'Clear search';
        
        searchContainer.appendChild(searchInput);
        searchContainer.appendChild(clearBtn);
        
        // Wrap select
        const parent = select.parentNode;
        parent.insertBefore(wrapper, select);
        wrapper.appendChild(searchContainer);
        wrapper.appendChild(select);
        
        // Store original options for filtering
        const originalOptions = Array.from(select.options).map(opt => ({
            value: opt.value,
            text: opt.textContent,
            selected: opt.selected
        }));
        
        // Show search when dropdown is clicked/focused
        select.addEventListener('mousedown', function(e) {
            if (this.options.length > 5) {
                searchInput.style.display = 'block';
                setTimeout(() => searchInput.focus(), 10);
            }
        });
        
        select.addEventListener('focus', function() {
            if (this.options.length > 5) {
                searchInput.style.display = 'block';
            }
        });
        
        // Filter options as user types
        searchInput.addEventListener('input', function() {
            const term = this.value.toLowerCase().trim();
            clearBtn.style.display = term ? 'block' : 'none';
            filterDropdownOptions(select, term, originalOptions);
        });
        
        // Clear search
        clearBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            searchInput.value = '';
            clearBtn.style.display = 'none';
            filterDropdownOptions(select, '', originalOptions);
            searchInput.focus();
        });
        
        // Hide search when dropdown loses focus
        select.addEventListener('blur', function(e) {
            setTimeout(() => {
                if (!wrapper.contains(document.activeElement)) {
                    searchInput.style.display = 'none';
                    searchInput.value = '';
                    clearBtn.style.display = 'none';
                    filterDropdownOptions(select, '', originalOptions);
                }
            }, 200);
        });
        
        // Handle Enter key in search - select first visible option
        searchInput.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                const visibleOptions = Array.from(select.options).filter(opt => opt.style.display !== 'none' && opt.value !== '');
                if (visibleOptions.length > 0) {
                    select.value = visibleOptions[0].value;
                    select.dispatchEvent(new Event('change'));
                    select.blur();
                }
            } else if (e.key === 'Escape') {
                searchInput.value = '';
                clearBtn.style.display = 'none';
                filterDropdownOptions(select, '', originalOptions);
                select.focus();
            }
        });
        
        // Prevent event bubbling
        searchInput.addEventListener('mousedown', function(e) {
            e.stopPropagation();
        });
        
        clearBtn.addEventListener('mousedown', function(e) {
            e.stopPropagation();
        });
    });
}

function filterDropdownOptions(select, searchTerm, originalOptions) {
    const term = searchTerm.toLowerCase();
    
    // Clear current options (except the first empty/default one)
    const firstOption = select.options[0];
    const firstValue = firstOption ? firstOption.value : '';
    const firstText = firstOption ? firstOption.textContent : '';
    
    // Remove all options
    while (select.options.length > 0) {
        select.remove(0);
    }
    
    // Add back the first/default option
    if (firstValue === '' || firstText.toLowerCase().includes('select') || firstText.toLowerCase().includes('all')) {
        const defaultOpt = document.createElement('option');
        defaultOpt.value = firstValue;
        defaultOpt.textContent = firstText;
        select.appendChild(defaultOpt);
    }
    
    // Add filtered options
    originalOptions.forEach(opt => {
        // Skip the first/default option
        if (opt.value === firstValue && opt.text === firstText) {
            return;
        }
        
        const text = opt.text.toLowerCase();
        if (!term || text.includes(term) || opt.value.toLowerCase().includes(term)) {
            const option = document.createElement('option');
            option.value = opt.value;
            option.textContent = opt.text;
            if (opt.selected) {
                option.selected = true;
            }
            select.appendChild(option);
        }
    });
    
    // If no results, show message
    if (term && select.options.length === 1 && select.options[0].value === firstValue) {
        const noResultOpt = document.createElement('option');
        noResultOpt.value = '';
        noResultOpt.textContent = 'No results found';
        noResultOpt.disabled = true;
        select.appendChild(noResultOpt);
    }
}
