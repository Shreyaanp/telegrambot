// Advanced Search Functionality for Documentation

// ============================================
// Search Data Structure
// ============================================
const searchData = {
  commands: [
    { name: '/start', category: 'User', description: 'Get started with the bot', page: 'commands.html#start' },
    { name: '/verify', category: 'User', description: 'Verify your identity with Mercle', page: 'commands.html#verify' },
    { name: '/status', category: 'User', description: 'Check your verification status', page: 'commands.html#status' },
    { name: '/help', category: 'User', description: 'Show help message', page: 'commands.html#help' },
    { name: '/rules', category: 'User', description: 'View group rules', page: 'commands.html#rules' },
    
    { name: '/settings', category: 'Admin', description: 'Configure bot settings', page: 'commands.html#settings' },
    { name: '/vkick', category: 'Admin', description: 'Kick user from group', page: 'commands.html#vkick' },
    { name: '/vban', category: 'Admin', description: 'Ban user from group', page: 'commands.html#vban' },
    { name: '/vverify', category: 'Admin', description: 'Manually verify user', page: 'commands.html#vverify' },
    { name: '/warn', category: 'Admin', description: 'Warn user', page: 'commands.html#warn' },
    { name: '/warnings', category: 'Admin', description: 'Show user warnings', page: 'commands.html#warnings' },
    { name: '/resetwarns', category: 'Admin', description: 'Clear user warnings', page: 'commands.html#resetwarns' },
    { name: '/whitelist', category: 'Admin', description: 'Manage whitelist', page: 'commands.html#whitelist' },
    { name: '/setwelcome', category: 'Admin', description: 'Set welcome message', page: 'commands.html#setwelcome' },
    { name: '/setgoodbye', category: 'Admin', description: 'Set goodbye message', page: 'commands.html#setgoodbye' },
    { name: '/goodbye', category: 'Admin', description: 'Enable/disable goodbye messages', page: 'commands.html#goodbye' },
    { name: '/filter', category: 'Admin', description: 'Add message filter', page: 'commands.html#filter' },
    { name: '/filters', category: 'Admin', description: 'List all filters', page: 'commands.html#filters' },
    { name: '/stop', category: 'Admin', description: 'Remove filter', page: 'commands.html#stop' },
    { name: '/lock', category: 'Admin', description: 'Lock message type', page: 'commands.html#lock' },
    { name: '/unlock', category: 'Admin', description: 'Unlock message type', page: 'commands.html#unlock' },
    { name: '/locks', category: 'Admin', description: 'Show current locks', page: 'commands.html#locks' },
    { name: '/save', category: 'Admin', description: 'Save note', page: 'commands.html#save' },
    { name: '/get', category: 'Admin', description: 'Get note', page: 'commands.html#get' },
    { name: '/notes', category: 'Admin', description: 'List all notes', page: 'commands.html#notes' },
    { name: '/clear', category: 'Admin', description: 'Delete note', page: 'commands.html#clear' },
    { name: '/adminlog', category: 'Admin', description: 'View admin action logs', page: 'commands.html#adminlog' },
  ],
  
  features: [
    { name: 'Biometric Verification', description: 'Secure face verification powered by Mercle SDK', page: 'features.html#verification' },
    { name: 'Admin Tools', description: 'Powerful moderation commands', page: 'features.html#admin' },
    { name: 'Welcome Messages', description: 'Custom welcome messages with buttons', page: 'features.html#greetings' },
    { name: 'Goodbye Messages', description: 'Farewell messages when users leave', page: 'features.html#greetings' },
    { name: 'Message Filters', description: 'Auto-respond to keywords', page: 'features.html#filters' },
    { name: 'Message Locks', description: 'Restrict message types', page: 'features.html#locks' },
    { name: 'Notes System', description: 'Save and retrieve group notes', page: 'features.html#notes' },
    { name: 'Admin Logs', description: 'Track admin actions', page: 'features.html#logs' },
    { name: 'Anti-Flood', description: 'Rate limiting protection', page: 'features.html#antiflood' },
    { name: 'Warnings System', description: 'Warn users and track violations', page: 'features.html#warnings' },
    { name: 'Whitelist', description: 'Bypass verification for trusted users', page: 'features.html#whitelist' },
  ],
  
  pages: [
    { name: 'Home', description: 'Bot overview and features', page: 'index.html' },
    { name: 'Features', description: 'Detailed feature documentation', page: 'features.html' },
    { name: 'Commands', description: 'Complete command reference', page: 'commands.html' },
    { name: 'Setup Guide', description: 'How to set up the bot', page: 'setup.html' },
    { name: 'API Documentation', description: 'Integration and API details', page: 'api.html' },
  ]
};

// ============================================
// Search Function
// ============================================
function performSearch(query) {
  query = query.toLowerCase().trim();
  if (!query) return [];
  
  const results = [];
  
  // Search commands
  searchData.commands.forEach(item => {
    const score = calculateRelevance(query, item.name, item.description);
    if (score > 0) {
      results.push({ ...item, type: 'Command', score });
    }
  });
  
  // Search features
  searchData.features.forEach(item => {
    const score = calculateRelevance(query, item.name, item.description);
    if (score > 0) {
      results.push({ ...item, type: 'Feature', score });
    }
  });
  
  // Search pages
  searchData.pages.forEach(item => {
    const score = calculateRelevance(query, item.name, item.description);
    if (score > 0) {
      results.push({ ...item, type: 'Page', score });
    }
  });
  
  // Sort by relevance
  results.sort((a, b) => b.score - a.score);
  
  return results.slice(0, 10); // Return top 10 results
}

// ============================================
// Relevance Calculation
// ============================================
function calculateRelevance(query, name, description) {
  let score = 0;
  const queryLower = query.toLowerCase();
  const nameLower = name.toLowerCase();
  const descLower = description.toLowerCase();
  
  // Exact match in name
  if (nameLower === queryLower) {
    score += 100;
  }
  // Starts with query in name
  else if (nameLower.startsWith(queryLower)) {
    score += 50;
  }
  // Contains query in name
  else if (nameLower.includes(queryLower)) {
    score += 30;
  }
  
  // Contains query in description
  if (descLower.includes(queryLower)) {
    score += 10;
  }
  
  // Bonus for shorter names (more specific)
  if (score > 0) {
    score += Math.max(0, 20 - name.length);
  }
  
  return score;
}

// ============================================
// Search UI
// ============================================
function createSearchResults(results) {
  if (results.length === 0) {
    return '<div class="search-no-results">No results found</div>';
  }
  
  let html = '<div class="search-results">';
  
  results.forEach(result => {
    const icon = getTypeIcon(result.type);
    const badge = result.category ? `<span class="badge ${result.category.toLowerCase()}">${result.category}</span>` : '';
    
    html += `
      <a href="/docs/${result.page}" class="search-result-item">
        <div class="search-result-icon">${icon}</div>
        <div class="search-result-content">
          <div class="search-result-title">
            ${result.name}
            ${badge}
          </div>
          <div class="search-result-description">${result.description}</div>
          <div class="search-result-type">${result.type}</div>
        </div>
      </a>
    `;
  });
  
  html += '</div>';
  return html;
}

function getTypeIcon(type) {
  const icons = {
    'Command': '⌨️',
    'Feature': '✨',
    'Page': '📄'
  };
  return icons[type] || '📌';
}

// ============================================
// Search Modal
// ============================================
function createSearchModal() {
  const modal = document.createElement('div');
  modal.className = 'search-modal';
  modal.innerHTML = `
    <div class="search-modal-overlay"></div>
    <div class="search-modal-content">
      <div class="search-modal-header">
        <input type="text" class="search-modal-input" placeholder="Search documentation..." autofocus>
        <button class="search-modal-close">✕</button>
      </div>
      <div class="search-modal-results"></div>
      <div class="search-modal-footer">
        <span>↑↓ Navigate</span>
        <span>↵ Select</span>
        <span>Esc Close</span>
      </div>
    </div>
  `;
  
  document.body.appendChild(modal);
  
  // Add styles
  const style = document.createElement('style');
  style.textContent = `
    .search-modal {
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      z-index: 10000;
      display: none;
    }
    
    .search-modal.active {
      display: block;
    }
    
    .search-modal-overlay {
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(0, 0, 0, 0.7);
      backdrop-filter: blur(4px);
    }
    
    .search-modal-content {
      position: absolute;
      top: 10%;
      left: 50%;
      transform: translateX(-50%);
      width: 90%;
      max-width: 600px;
      background: var(--bg-primary);
      border-radius: 12px;
      box-shadow: var(--shadow-lg);
      overflow: hidden;
    }
    
    .search-modal-header {
      display: flex;
      align-items: center;
      padding: 1rem;
      border-bottom: 1px solid var(--border-color);
    }
    
    .search-modal-input {
      flex: 1;
      border: none;
      background: none;
      font-size: 1.1rem;
      color: var(--text-primary);
      outline: none;
    }
    
    .search-modal-close {
      background: none;
      border: none;
      font-size: 1.5rem;
      color: var(--text-secondary);
      cursor: pointer;
      padding: 0.5rem;
    }
    
    .search-modal-results {
      max-height: 400px;
      overflow-y: auto;
      padding: 0.5rem;
    }
    
    .search-result-item {
      display: flex;
      align-items: start;
      gap: 1rem;
      padding: 1rem;
      border-radius: 8px;
      text-decoration: none;
      color: var(--text-primary);
      transition: background var(--transition-fast);
    }
    
    .search-result-item:hover,
    .search-result-item.selected {
      background: var(--bg-secondary);
    }
    
    .search-result-icon {
      font-size: 1.5rem;
    }
    
    .search-result-content {
      flex: 1;
    }
    
    .search-result-title {
      font-weight: 500;
      margin-bottom: 0.25rem;
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }
    
    .search-result-description {
      font-size: 0.9rem;
      color: var(--text-secondary);
    }
    
    .search-result-type {
      font-size: 0.75rem;
      color: var(--text-tertiary);
      margin-top: 0.25rem;
    }
    
    .search-modal-footer {
      display: flex;
      gap: 1rem;
      padding: 0.75rem 1rem;
      background: var(--bg-secondary);
      border-top: 1px solid var(--border-color);
      font-size: 0.85rem;
      color: var(--text-secondary);
    }
    
    .search-no-results {
      padding: 2rem;
      text-align: center;
      color: var(--text-secondary);
    }
  `;
  document.head.appendChild(style);
  
  return modal;
}

// ============================================
// Initialize Search
// ============================================
const searchModal = createSearchModal();
const searchInput = searchModal.querySelector('.search-modal-input');
const searchResults = searchModal.querySelector('.search-modal-results');
const searchClose = searchModal.querySelector('.search-modal-close');
const searchOverlay = searchModal.querySelector('.search-modal-overlay');

let selectedIndex = 0;

// Open search modal
document.addEventListener('keydown', (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
    e.preventDefault();
    searchModal.classList.add('active');
    searchInput.focus();
  }
});

// Close search modal
searchClose.addEventListener('click', () => {
  searchModal.classList.remove('active');
  searchInput.value = '';
  searchResults.innerHTML = '';
});

searchOverlay.addEventListener('click', () => {
  searchModal.classList.remove('active');
  searchInput.value = '';
  searchResults.innerHTML = '';
});

// Search on input
searchInput.addEventListener('input', (e) => {
  const query = e.target.value;
  const results = performSearch(query);
  searchResults.innerHTML = createSearchResults(results);
  selectedIndex = 0;
  updateSelectedResult();
});

// Keyboard navigation
searchInput.addEventListener('keydown', (e) => {
  const resultItems = searchResults.querySelectorAll('.search-result-item');
  
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    selectedIndex = Math.min(selectedIndex + 1, resultItems.length - 1);
    updateSelectedResult();
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    selectedIndex = Math.max(selectedIndex - 1, 0);
    updateSelectedResult();
  } else if (e.key === 'Enter') {
    e.preventDefault();
    if (resultItems[selectedIndex]) {
      resultItems[selectedIndex].click();
    }
  } else if (e.key === 'Escape') {
    searchModal.classList.remove('active');
    searchInput.value = '';
    searchResults.innerHTML = '';
  }
});

function updateSelectedResult() {
  const resultItems = searchResults.querySelectorAll('.search-result-item');
  resultItems.forEach((item, index) => {
    item.classList.toggle('selected', index === selectedIndex);
  });
  
  if (resultItems[selectedIndex]) {
    resultItems[selectedIndex].scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }
}

console.log('Search functionality initialized! 🔍');
console.log('Press Ctrl/Cmd + K to search');

