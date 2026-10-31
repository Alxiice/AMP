# Signing in

Signing in is **optional**. Search and playback work without it. Signing in adds:

- your liked songs (**Library** page),
- your playlists (**Playlists** page),
- songs YouTube only serves to signed-in users (age-restricted ones, for example).

Open the **Auth** page from the sidebar, or click the session badge.

## Sign in with YouTube (recommended)

Desktop app only.

1. Click **Sign in with YouTube**.
2. A private window opens on Google's sign-in page. Sign in as usual (password, 2FA…).
3. When Google sends you on to YouTube Music, the window closes by itself and the badge turns
   to **Signed in**.

The window has no saved Google session, so you sign in from scratch each time. You have
10 minutes. Closing the window cancels.

## Advanced methods

Under **Advanced** on the Auth page. Use these in the browser version of the app, or if the
sign-in window doesn't work for you.

??? abstract "Paste a Cookie header"
    1. Open [music.youtube.com](https://music.youtube.com) in your browser and sign in.
    2. Open the developer tools (++f12++) → **Network** tab → reload the page.
    3. Click any request to `music.youtube.com` and copy the value of its `Cookie` request header.
    4. Paste it into the text box and click **Set Cookies**.

??? abstract "Import from Firefox"
    1. Sign in to YouTube Music in Firefox.
    2. **Close Firefox**: its cookie database is locked while it runs.
    3. Click **Import from Firefox**.

    Chrome, Edge and Brave aren't supported: on Windows their cookies are encrypted in a way
    other programs can't read.

## What is stored

- Only **youtube.com cookies** are kept, whatever the method. Cookies of other sites (Google
  accounts, your bank…) are dropped before anything is saved.
- They are saved in `cache/ytm_session.json` in the
  [data directory](configuration.md#where-amp-keeps-its-data), readable only by your user on
  Linux/macOS.
- Cookie values never appear in the logs.

**Logout** on the Auth page deletes the file.

## Session expired

YouTube sessions eventually expire. The badge then reads **Session expired — reconnect**, and
Library/Playlists show the sign-in prompt again. Sign in again the same way.

!!! note "Desktop app vs. manual runs keep separate sign-ins"
    The desktop app and a backend you start by hand (or with `app.py`) use different data
    folders, so signing in to one doesn't sign in the other. See
    [Configuration](configuration.md#where-amp-keeps-its-data).

??? info "\"Your saved session came from an older version…\" warning"
    Very old versions of AMP saved every cookie from your browser when importing. On startup AMP
    now trims such a file to YouTube's session cookies only. If it held many more cookies than
    that, the Auth page shows a warning until you sign in again. Signing in again is
    recommended: it replaces the trimmed file with a clean one.
