// Sidebar Navigation and Search Functionality

// ============================================
// Search Functionality
// ============================================
const searchInput = document.querySelector('.search-box input');
const navMenu = document.querySelector('.nav-menu');

if (searchInput && navMenu) {
  const allNavItems = Array.from(navMenu.querySelectorAll('li:not(.nav-section)'));
  const allSections = Array.from(navMenu.querySelectorAll('.nav-section'));
  
  searchInput.addEventListener('input', (e) => {
    const searchTerm = e.target.value.toLowerCase().trim();
    
    if (searchTerm === '') {
      // Show all items
      allNavItems.forEach(item => item.style.display = '');
      allSections.forEach(section => section.style.display = '');
      return;
    }
    
    // Filter items
    allNavItems.forEach(item => {
      const link = item.querySelector('a');
      if (link) {
        const text = link.textContent.toLowerCase();
        if (text.includes(searchTerm)) {
          item.style.display = '';
          // Highlight matching text
          const regex = new RegExp(`(${searchTerm})`, 'gi');
          link.innerHTML = link.textContent.replace(regex, '<mark>$1</mark>');
        } else {
          item.style.display = 'none';
        }
      }
    });
    
    // Hide sections if no items are visible under them
    allSections.forEach(section => {
      let nextElement = section.nextElementSibling;
      let hasVisibleItems = false;
      
      while (nextElement && !nextElement.classList.contains('nav-section')) {
        if (nextElement.style.display !== 'none') {
          hasVisibleItems = true;
          break;
        }
        nextElement = nextElement.nextElementSibling;
      }
      
      section.style.display = hasVisibleItems ? '' : 'none';
    });
  });
  
  // Clear highlights when search is cleared
  searchInput.addEventListener('blur', () => {
    setTimeout(() => {
      allNavItems.forEach(item => {
        const link = item.querySelector('a');
        if (link) {
          const text = link.textContent;
          link.innerHTML = text;
        }
      });
    }, 200);
  });
}

// ============================================
// Collapsible Sections
// ============================================
function initCollapsibleSections() {
  const sections = document.querySelectorAll('.nav-section');
  
  sections.forEach(section => {
    section.style.cursor = 'pointer';
    section.style.userSelect = 'none';
    
    // Add collapse icon
    const icon = document.createElement('span');
    icon.className = 'collapse-icon';
    icon.textContent = '▼';
    icon.style.cssText = `
      float: right;
      transition: transform 0.3s ease;
      font-size: 0.7rem;
    `;
    section.appendChild(icon);
    
    section.addEventListener('click', () => {
      let nextElement = section.nextElementSibling;
      const isCollapsed = section.classList.contains('collapsed');
      
      // Toggle items under this section
      while (nextElement && !nextElement.classList.contains('nav-section')) {
        if (isCollapsed) {
          nextElement.style.display = '';
        } else {
          nextElement.style.display = 'none';
        }
        nextElement = nextElement.nextElementSibling;
      }
      
      // Toggle collapsed state
      section.classList.toggle('collapsed');
      icon.style.transform = isCollapsed ? 'rotate(0deg)' : 'rotate(-90deg)';
    });
  });
}

// Initialize collapsible sections
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initCollapsibleSections);
} else {
  initCollapsibleSections();
}

// ============================================
// Keyboard Navigation
// ============================================
document.addEventListener('keydown', (e) => {
  // Ctrl/Cmd + K to focus search
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
    e.preventDefault();
    if (searchInput) {
      searchInput.focus();
    }
  }
  
  // Escape to clear search
  if (e.key === 'Escape' && searchInput === document.activeElement) {
    searchInput.value = '';
    searchInput.dispatchEvent(new Event('input'));
    searchInput.blur();
  }
});

// ============================================
// Sidebar Resize Handler
// ============================================
let isResizing = false;
const sidebar = document.querySelector('.sidebar');
const mainContent = document.querySelector('.main-content');

function initSidebarResize() {
  const resizeHandle = document.createElement('div');
  resizeHandle.className = 'sidebar-resize-handle';
  resizeHandle.style.cssText = `
    position: absolute;
    right: 0;
    top: 0;
    bottom: 0;
    width: 5px;
    cursor: ew-resize;
    background: transparent;
    z-index: 10;
  `;
  
  sidebar.appendChild(resizeHandle);
  
  resizeHandle.addEventListener('mousedown', (e) => {
    isResizing = true;
    document.body.style.cursor = 'ew-resize';
    document.body.style.userSelect = 'none';
  });
  
  document.addEventListener('mousemove', (e) => {
    if (!isResizing) return;
    
    const newWidth = e.clientX;
    if (newWidth >= 200 && newWidth <= 400) {
      sidebar.style.width = `${newWidth}px`;
      mainContent.style.marginLeft = `${newWidth}px`;
      document.documentElement.style.setProperty('--sidebar-width', `${newWidth}px`);
    }
  });
  
  document.addEventListener('mouseup', () => {
    if (isResizing) {
      isResizing = false;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      
      // Save width to localStorage
      const width = sidebar.style.width;
      if (width) {
        localStorage.setItem('sidebar-width', width);
      }
    }
  });
  
  // Load saved width
  const savedWidth = localStorage.getItem('sidebar-width');
  if (savedWidth) {
    sidebar.style.width = savedWidth;
    mainContent.style.marginLeft = savedWidth;
    document.documentElement.style.setProperty('--sidebar-width', savedWidth);
  }
}

// Only enable resize on desktop
if (window.innerWidth > 768) {
  initSidebarResize();
}

// ============================================
// Active Link Tracking on Scroll
// ============================================
function trackActiveLink() {
  const links = document.querySelectorAll('.nav-menu a[href^="#"]');
  const sections = [];
  
  links.forEach(link => {
    const href = link.getAttribute('href');
    const section = document.querySelector(href);
    if (section) {
      sections.push({ link, section });
    }
  });
  
  function updateActiveLink() {
    const scrollPosition = window.scrollY + 100;
    
    for (let i = sections.length - 1; i >= 0; i--) {
      const { link, section } = sections[i];
      if (section.offsetTop <= scrollPosition) {
        links.forEach(l => l.classList.remove('active'));
        link.classList.add('active');
        
        // Scroll sidebar to show active link
        const linkTop = link.offsetTop;
        const sidebarScroll = sidebar.scrollTop;
        const sidebarHeight = sidebar.clientHeight;
        
        if (linkTop < sidebarScroll || linkTop > sidebarScroll + sidebarHeight) {
          link.scrollIntoView({ block: 'center', behavior: 'smooth' });
        }
        
        break;
      }
    }
  }
  
  window.addEventListener('scroll', updateActiveLink);
  updateActiveLink();
}

trackActiveLink();

// ============================================
// Breadcrumbs
// ============================================
function generateBreadcrumbs() {
  const breadcrumbContainer = document.querySelector('.breadcrumbs');
  if (!breadcrumbContainer) return;
  
  const path = window.location.pathname;
  const segments = path.split('/').filter(s => s);
  
  let breadcrumbHTML = '<a href="/docs/">Home</a>';
  let currentPath = '/docs';
  
  segments.forEach((segment, index) => {
    if (segment === 'docs') return;
    
    currentPath += '/' + segment;
    const isLast = index === segments.length - 1;
    const label = segment.replace('.html', '').replace(/-/g, ' ');
    const capitalizedLabel = label.charAt(0).toUpperCase() + label.slice(1);
    
    if (isLast) {
      breadcrumbHTML += ` / <span>${capitalizedLabel}</span>`;
    } else {
      breadcrumbHTML += ` / <a href="${currentPath}">${capitalizedLabel}</a>`;
    }
  });
  
  breadcrumbContainer.innerHTML = breadcrumbHTML;
}

generateBreadcrumbs();

console.log('Sidebar navigation initialized! 📚');

