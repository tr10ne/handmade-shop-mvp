window.APP_CONFIG = {
  API_BASE: window.location.hostname === 'localhost' 
    ? 'http://localhost:8001' 
    : '/api',
  MEDIA_BASE: window.location.hostname === 'localhost'
    ? 'http://localhost:8001/media'
    : '/api/media',
  STOREFRONT_URL: window.location.hostname === 'localhost'
    ? 'http://localhost:3000'
    : '/',
  ADMIN_URL: window.location.hostname === 'localhost'
    ? 'http://localhost:3001'
    : '/admin',
  UPLOAD_ENDPOINT: '/upload/images',
  PRODUCTS_ENDPOINT: '/products/',
  CATEGORIES_ENDPOINT: '/categories/',
  AUCTIONS_ENDPOINT: '/auctions/',
  REQUEST_TIMEOUT_MS: 15000,
};
