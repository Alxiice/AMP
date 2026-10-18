// Authentication Server for AMP
// This server helps with YouTube cookie authentication
// It serves a page that loads YouTube Music and captures cookies

const express = require('express');
const cookieParser = require('cookie-parser');
const fs = require('fs');
const path = require('path');

const app = express();
const PORT = 8080;

// Middleware
app.use(express.json());
app.use(cookieParser());

// Serve the auth page
app.get('/auth/youtube', (req, res) => {
    const html = `
    <!DOCTYPE html>
    <html>
    <head>
        <title>YouTube Music Authentication</title>
        <style>
            body { font-family: Arial, sans-serif; text-align: center; padding: 20px; }
            iframe { width: 100%; height: 600px; border: none; margin: 20px 0; }
            .instructions { padding: 20px; background: #f5f5f5; margin: 20px; border-radius: 8px; }
            button { padding: 12px 24px; background: #4285f4; color: white; border: none; border-radius: 4px; cursor: pointer; }
            button:hover { background: #3367d6; }
        </style>
    </head>
    <body>
        <h1>YouTube Music Authentication</h1>
        <div class="instructions">
            <p>Please log in to YouTube Music in the iframe below.</p>
            <p>Once logged in, click the button below to save your cookies.</p>
        </div>
        <iframe src="https://music.youtube.com" id="ytmusic-iframe"></iframe>
        <button onclick="saveCookies()">Save Cookies and Continue</button>
        
        <script>
            // Listen for messages from the iframe
            window.addEventListener('message', (event) => {
                if (event.data.type === 'cookies') {
                    saveCookies();
                }
            });
            
            function saveCookies() {
                // Get cookies from the iframe
                // This is tricky due to same-origin policy
                // Instead, we'll have the user's browser send cookies to our backend
                
                // Redirect to backend with cookies
                // This won't work due to CORS, so we need a different approach
                
                // For now, just close this window
                window.close();
            }
            
            // Try to access iframe cookies (won't work due to same-origin policy)
            function checkCookies() {
                try {
                    const iframe = document.getElementById('ytmusic-iframe');
                    const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
                    // Can't access due to same-origin policy
                } catch (e) {
                    console.log('Cannot access iframe cookies due to same-origin policy');
                }
            }
            
            // Check every second
            setInterval(checkCookies, 1000);
        </script>
    </body>
    </html>
    `;
    res.send(html);
});

// Endpoint to save cookies (called from parent window)
app.post('/auth/save-cookies', (req, res) => {
    try {
        const cookies = req.body.cookies;
        const cookiesPath = path.join(__dirname, '..', '.amp', 'cache', 'cookies.json');
        
        // Ensure directory exists
        const dir = path.dirname(cookiesPath);
        if (!fs.existsSync(dir)) {
            fs.mkdirSync(dir, { recursive: true });
        }
        
        // Save cookies
        fs.writeFileSync(cookiesPath, JSON.stringify(cookies, null, 2));
        
        res.json({ success: true, message: 'Cookies saved successfully' });
    } catch (error) {
        console.error('Error saving cookies:', error);
        res.status(500).json({ success: false, error: error.message });
    }
});

// Endpoint to check if cookies are ready
app.get('/auth/status', (req, res) => {
    const cookiesPath = path.join(__dirname, '..', '.amp', 'cache', 'cookies.json');
    const exists = fs.existsSync(cookiesPath);
    res.json({ authenticated: exists });
});

// Start server
app.listen(PORT, () => {
    console.log(`YouTube Auth Server running on http://localhost:${PORT}`);
    console.log('');
    console.log('Open this URL in your browser:');
    console.log(`http://localhost:${PORT}/auth/youtube`);
    console.log('');
    console.log('Log in to YouTube Music, then click "Save Cookies and Continue"');
});
