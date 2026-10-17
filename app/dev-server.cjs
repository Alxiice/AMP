const express = require('express');
const { createProxyMiddleware } = require('http-proxy-middleware');

const app = express();
const PORT = 3000;

// Serve static files from the dist directory
app.use(express.static('dist'));

// Proxy API requests to the backend
app.use(
  '/api',
  createProxyMiddleware({
    target: 'http://localhost:8000',
    changeOrigin: true,
    pathRewrite: {
      '^/api': '/api', // Keep /api prefix
    },
  })
);

// Fallback to index.html for all other routes (for SPA routing)
app.get('*', (req, res) => {
  res.sendFile(__dirname + '/dist/index.html');
});

app.listen(PORT, () => {
  console.log(`AMP Frontend Dev Server running on http://localhost:${PORT}`);
  console.log('Proxying /api/* to http://localhost:8000');
  console.log('');
  console.log('Make sure the backend is running:');
  console.log('  python amp/backend/main.py');
  console.log('');
  console.log(`Then open: http://localhost:${PORT}`);
});
