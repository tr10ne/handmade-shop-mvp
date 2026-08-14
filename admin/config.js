window.APP_CONFIG = {
  API_BASE: window.location.hostname === 'localhost' 
    ? 'http://localhost:8001' 
    : 'http://127.0.0.1:8001',
  MEDIA_BASE: window.location.hostname === 'localhost'
    ? 'http://localhost:8001/media'
    : 'http://127.0.0.1:8001/media',
  STOREFRONT_URL: window.location.hostname === 'localhost'
    ? 'http://localhost:3000'
    : 'http://127.0.0.1:3000',
  ADMIN_URL: window.location.hostname === 'localhost'
    ? 'http://localhost:3001'
    : 'http://127.0.0.1:3001',
  UPLOAD_ENDPOINT: '/upload/images',
  PRODUCTS_ENDPOINT: '/products/',
  CATEGORIES_ENDPOINT: '/categories/',
  AUCTIONS_ENDPOINT: '/auctions/',
  REQUEST_TIMEOUT_MS: 15000,
};
