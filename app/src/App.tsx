import { useState, useEffect } from 'react';

// Backend API base URL
const BACKEND_URL = 'http://localhost:8000';

// Types for our data
type Song = {
  id: string;
  title: string;
  artist: string | null;
  album: string | null;
  thumbnail_url: string | null;
  duration_ms: number | null;
  year: number | null;
};

type AuthStatus = {
  is_authenticated: boolean;
  has_tokens: boolean;
  user_info: any;
  client_configured: boolean;
  auth_in_progress?: boolean;
  auth_message?: string;
  youtube_url?: string;
  auth_type?: 'oauth' | 'cookies';
  is_automated?: boolean;
  warning?: string;
};

function App() {
  const [authStatus, setAuthStatus] = useState<AuthStatus | null>(null);
  const [likedSongs, setLikedSongs] = useState<Song[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Check auth status on mount
  useEffect(() => {
    checkAuthStatus();
  }, []);

  const checkAuthStatus = async () => {
    try {
      const response = await fetch(`${BACKEND_URL}/api/auth/status`);
      if (response.ok) {
        const data = await response.json();
        setAuthStatus(data);
        
        // If already authenticated, load liked songs
        if (data.is_authenticated) {
          await loadLikedSongs();
        }
      }
    } catch (err) {
      setError('Failed to check authentication status');
      console.error('Auth status check failed:', err);
    }
  };

  const loadLikedSongs = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const response = await fetch(`${BACKEND_URL}/api/user/likes`);
      
      if (response.status === 401) {
        // Not authenticated
        setAuthStatus({ ...authStatus, is_authenticated: false });
        setLikedSongs([]);
        return;
      }
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const songs = await response.json();
      setLikedSongs(songs);
    } catch (err) {
      setError('Failed to load liked songs');
      console.error('Load liked songs failed:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleLogin = async () => {
    try {
      setLoading(true);
      setError(null);
      
      // Try OAuth login first (if credentials are configured)
      const oauthResponse = await fetch(`${BACKEND_URL}/api/auth/login`, {
        method: 'POST',
      });
      
      if (oauthResponse.ok) {
        const oauthData = await oauthResponse.json();
        
        // If we got an auth_url, open it in a new window/tab
        if (oauthData.auth_url) {
          console.log('OAuth URL:', oauthData.auth_url);
          
          // For web: open in new tab
          // For Tauri: use shell.open
          if (window.__TAURI__) {
            // Tauri app - use shell plugin
            try {
              const { open } = await import('@tauri-apps/plugin-shell');
              await open(oauthData.auth_url);
            } catch (e) {
              // Fallback to window.open
              window.open(oauthData.auth_url, '_blank');
            }
          } else {
            // Regular web - open in new tab
            window.open(oauthData.auth_url, '_blank');
          }
          
          // Show message to user
          setAuthStatus({
            ...authStatus,
            is_authenticated: false,
            auth_in_progress: true,
            auth_message: 'Browser opened for authentication. Please complete login and return to this page.'
          });
          
          // Start polling for auth completion
          const checkInterval = setInterval(async () => {
            await checkAuthStatus();
            if (authStatus?.is_authenticated) {
              clearInterval(checkInterval);
              setLoading(false);
            }
          }, 2000);
          
          // Clear interval after 2 minutes
          setTimeout(() => {
            clearInterval(checkInterval);
            if (!authStatus?.is_authenticated) {
              setAuthStatus({
                ...authStatus,
                auth_in_progress: false,
                auth_message: 'Authentication timed out. Please try again.'
              });
              setLoading(false);
            }
          }, 120000);
          
          return;
        }
      }
      
      // Fallback to cookie-based auth if OAuth not configured
      console.log('OAuth not configured, falling back to cookie-based auth');
      const response = await fetch(`${BACKEND_URL}/api/auth/cookie-auth`, {
        method: 'POST',
      });
      
      if (!response.ok) {
        throw new Error('Failed to start authentication');
      }
      
      const data = await response.json();
      console.log('Auth triggered:', data.message);
      
      // Show success message to user
      setAuthStatus({
        ...authStatus,
        is_authenticated: false,
        auth_in_progress: true,
        auth_message: data.message,
        youtube_url: data.youtube_url
      });
      
      // If there's a YouTube URL, open it
      if (data.youtube_url) {
        if (window.__TAURI__) {
          try {
            const { open } = await import('@tauri-apps/plugin-shell');
            await open(data.youtube_url);
          } catch (e) {
            window.open(data.youtube_url, '_blank');
          }
        } else {
          window.open(data.youtube_url, '_blank');
        }
      }
      
      // Wait for user to complete manual auth
      const checkInterval = setInterval(async () => {
        await checkAuthStatus();
        if (authStatus?.is_authenticated) {
          clearInterval(checkInterval);
          setLoading(false);
        }
      }, 2000);
      
      // Clear interval after 60 seconds
      setTimeout(() => {
        clearInterval(checkInterval);
        if (!authStatus?.is_authenticated) {
          setAuthStatus({
            ...authStatus,
            auth_in_progress: false,
            auth_message: 'Authentication timed out. Please try again.'
          });
          setLoading(false);
        }
      }, 60000);
      
    } catch (err) {
      setError('Failed to start authentication');
      console.error('Login failed:', err);
      setLoading(false);
    }
  };

  const handleLogout = async () => {
    try {
      setLoading(true);
      const response = await fetch(`${BACKEND_URL}/api/auth/logout`, {
        method: 'POST',
      });
      
      if (response.ok) {
        setAuthStatus({ ...authStatus, is_authenticated: false });
        setLikedSongs([]);
      }
    } catch (err) {
      console.error('Logout failed:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="container">
      <h1>AMP</h1>
      <p className="powered-by">Powered by YouTube Music</p>
      
      {!authStatus?.is_authenticated ? (
        <div>
          <button 
            className="button" 
            onClick={handleLogin}
            disabled={loading}
          >
            {loading ? 'Opening browser...' : 'Login with YouTube Music'}
          </button>
          {authStatus?.auth_in_progress && (
            <div className="status" style={{ marginTop: '1rem' }}>
              {authStatus.is_automated ? (
                <p style={{ color: '#28a745' }}>
                  ✅ {authStatus.auth_message || 'Please complete authentication in the browser window that opened.'}
                </p>
              ) : (
                <div>
                  <p style={{ color: '#ffc107' }}>
                    ⚠️ {authStatus.auth_message || 'Please follow the instructions in the terminal.'}
                  </p>
                  <p style={{ color: '#666', fontSize: '0.9rem', marginTop: '0.5rem' }}>
                    For FULLY AUTOMATED auth (like Spotify):
                    <br />
                    <code style={{ background: '#f0f0f0', padding: '2px 6px', borderRadius: '4px' }}>
                      Create Google OAuth credentials
                    </code>
                  </p>
                </div>
              )}
            </div>
          )}
          {!authStatus?.auth_in_progress && authStatus?.warning && (
            <div className="status" style={{ marginTop: '1rem', color: '#666', fontSize: '0.9rem' }}>
              <p>{authStatus.warning}</p>
            </div>
          )}
        </div>
      ) : (
        <div>
          <button 
            className="button" 
            onClick={handleLogout}
            disabled={loading}
          >
            Logout
          </button>
          
          <div className="status">
            <h3>✓ Authenticated</h3>
            <p>You can now access your YouTube Music library.</p>
          </div>
          
          {loading && (
            <p className="loading">Loading your liked songs...</p>
          )}
          
          {error && (
            <p className="error">{error}</p>
          )}
          
          {likedSongs.length > 0 && (
            <div className="songs">
              <h3>Your Liked Songs ({likedSongs.length})</h3>
              {likedSongs.slice(0, 10).map((song) => (
                <div key={song.id} className="song">
                  {song.thumbnail_url && (
                    <img 
                      src={song.thumbnail_url} 
                      alt={song.title}
                      onError={(e) => {
                        (e.target as HTMLImageElement).style.display = 'none';
                      }}
                    />
                  )}
                  <div className="song-info">
                    <div className="song-title">{song.title}</div>
                    <div className="song-artist">{song.artist || 'Unknown Artist'}</div>
                  </div>
                </div>
              ))}
              {likedSongs.length > 10 && (
                <p style={{ color: '#666', fontSize: '0.85rem', marginTop: '1rem' }}>
                  ... and {likedSongs.length - 10} more
                </p>
              )}
            </div>
          )}
        </div>
      )}
      
      {error && (
        <p className="error">{error}</p>
      )}
      
      {!authStatus?.is_authenticated && !loading && (
        <div className="status">
          <h3>Not logged in</h3>
          <p>Click the button above to authenticate with YouTube Music and access your liked songs.</p>
        </div>
      )}
    </div>
  );
}

export default App;
