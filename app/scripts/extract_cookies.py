#!/usr/bin/env python3
"""
Cookie Extraction Script for YouTube Music

This script attempts to extract YouTube Music cookies from common browsers.
It supports:
- Google Chrome / Chromium / Edge (Windows, Mac, Linux)
- Mozilla Firefox (Windows, Mac, Linux)
- Safari (Mac only)

Usage:
    python extract_cookies.py [--browser chrome|firefox|edge|safari] [--output cookies.json]

Note: This requires the browser to be logged in to YouTube Music.
"""

import argparse
import json
import os
import platform
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def get_chrome_cookies(browser: str = "chrome") -> List[Dict]:
    """Extract cookies from Chrome/Chromium/Edge."""
    cookies = []
    
    system = platform.system()
    
    # Determine cookie file path based on OS and browser
    if system == "Windows":
        app_data = os.getenv("LOCALAPPDATA") or os.path.join(os.getenv("USERPROFILE"), "AppData", "Local")
        
        browser_paths = {
            "chrome": os.path.join(app_data, "Google", "Chrome", "User Data", "Default", "Cookies"),
            "chromium": os.path.join(app_data, "Chromium", "User Data", "Default", "Cookies"),
            "edge": os.path.join(app_data, "Microsoft", "Edge", "User Data", "Default", "Cookies"),
            "brave": os.path.join(app_data, "BraveSoftware", "Brave-Browser", "User Data", "Default", "Cookies"),
        }
        
    elif system == "Darwin":  # Mac
        home = os.path.expanduser("~")
        
        browser_paths = {
            "chrome": os.path.join(home, "Library", "Application Support", "Google", "Chrome", "Default", "Cookies"),
            "chromium": os.path.join(home, "Library", "Application Support", "Chromium", "Default", "Cookies"),
            "edge": os.path.join(home, "Library", "Application Support", "Microsoft Edge", "Default", "Cookies"),
            "brave": os.path.join(home, "Library", "Application Support", "BraveSoftware", "Brave-Browser", "Default", "Cookies"),
        }
        
    elif system == "Linux":
        home = os.path.expanduser("~")
        
        browser_paths = {
            "chrome": os.path.join(home, ".config", "google-chrome", "Default", "Cookies"),
            "chromium": os.path.join(home, ".config", "chromium", "Default", "Cookies"),
            "edge": os.path.join(home, ".config", "microsoft-edge", "Default", "Cookies"),
            "brave": os.path.join(home, ".config", "BraveSoftware", "Brave-Browser", "Default", "Cookies"),
        }
    else:
        return cookies
    
    cookie_path = browser_paths.get(browser.lower(), browser_paths["chrome"])
    
    if not os.path.exists(cookie_path):
        print(f"Chrome cookie file not found: {cookie_path}")
        return cookies
    
    # Chrome uses SQLite database for cookies
    try:
        conn = sqlite3.connect(cookie_path)
        cursor = conn.cursor()
        
        # Query for YouTube cookies
        cursor.execute("""
            SELECT name, value, domain, path, expires_utc, secure, httponly 
            FROM cookies 
            WHERE domain LIKE '%youtube%' OR domain LIKE '%google%' OR domain = '.youtube.com'
            ORDER BY domain
        """)
        
        rows = cursor.fetchall()
        
        for row in rows:
            name, value, domain, path, expires_utc, secure, httponly = row
            cookies.append({
                "name": name,
                "value": value,
                "domain": domain,
                "path": path,
                "expires": expires_utc,
                "secure": bool(secure),
                "httpOnly": bool(httponly)
            })
        
        conn.close()
        
    except Exception as e:
        print(f"Error reading Chrome cookies: {e}")
    
    return cookies


def get_firefox_cookies() -> List[Dict]:
    """Extract cookies from Firefox."""
    cookies = []
    
    system = platform.system()
    home = os.path.expanduser("~")
    
    if system == "Windows":
        firefox_path = os.path.join(os.getenv("APPDATA"), "Mozilla", "Firefox", "Profiles")
    elif system == "Darwin":
        firefox_path = os.path.join(home, "Library", "Application Support", "Firefox", "Profiles")
    elif system == "Linux":
        firefox_path = os.path.join(home, ".mozilla", "firefox")
    else:
        return cookies
    
    if not os.path.exists(firefox_path):
        print(f"Firefox profile directory not found: {firefox_path}")
        return cookies
    
    # Find the default profile
    profiles_ini = os.path.join(firefox_path, "profiles.ini")
    default_profile = None
    
    if os.path.exists(profiles_ini):
        with open(profiles_ini, 'r') as f:
            for line in f:
                if line.startswith("[Profile") or line.startswith("[Default"):
                    continue
                if "Default=1" in line:
                    profile_name = line.split('=')[1].strip()
                    default_profile = os.path.join(firefox_path, profile_name)
                    break
    
    # If no default profile, use the first one
    if not default_profile:
        for item in os.listdir(firefox_path):
            if item.endswith(".default") or os.path.isdir(os.path.join(firefox_path, item)):
                default_profile = os.path.join(firefox_path, item)
                break
    
    if not default_profile or not os.path.exists(default_profile):
        print("Could not find Firefox default profile")
        return cookies
    
    # Firefox uses SQLite for cookies
    cookie_file = os.path.join(default_profile, "cookies.sqlite")
    
    if not os.path.exists(cookie_file):
        print(f"Firefox cookies file not found: {cookie_file}")
        return cookies
    
    try:
        conn = sqlite3.connect(cookie_file)
        cursor = conn.cursor()
        
        # Firefox cookie format
        cursor.execute("""
            SELECT name, value, host, path, expiry, isSecure, isHttpOnly 
            FROM moz_cookies 
            WHERE host LIKE '%youtube%' OR host LIKE '%google%' OR host = '.youtube.com'
            ORDER BY host
        """)
        
        rows = cursor.fetchall()
        
        for row in rows:
            name, value, host, path, expiry, isSecure, isHttpOnly = row
            cookies.append({
                "name": name,
                "value": value,
                "domain": host,
                "path": path,
                "expires": expiry,
                "secure": bool(isSecure),
                "httpOnly": bool(isHttpOnly)
            })
        
        conn.close()
        
    except Exception as e:
        print(f"Error reading Firefox cookies: {e}")
    
    return cookies


def get_safari_cookies() -> List[Dict]:
    """Extract cookies from Safari (Mac only)."""
    if platform.system() != "Darwin":
        print("Safari cookie extraction only works on Mac")
        return []
    
    cookies = []
    home = os.path.expanduser("~")
    cookie_path = os.path.join(home, "Library", "Cookies", "Cookies.binarycookies")
    
    if not os.path.exists(cookie_path):
        print(f"Safari cookies file not found: {cookie_path}")
        return cookies
    
    # Safari uses binary cookie format - requires pyObjs or similar library
    print("Safari cookie extraction requires additional dependencies (pyObjC)")
    print("Consider using Chrome or Firefox instead")
    
    return cookies


def get_cookies_from_browser(browser: str) -> List[Dict]:
    """Get cookies from specified browser."""
    browser = browser.lower()
    
    if browser in ["chrome", "chromium", "edge", "brave"]:
        return get_chrome_cookies(browser)
    elif browser == "firefox":
        return get_firefox_cookies()
    elif browser == "safari":
        return get_safari_cookies()
    else:
        print(f"Unsupported browser: {browser}")
        return []


def filter_youtube_cookies(cookies: List[Dict]) -> Dict[str, str]:
    """Filter cookies to only YouTube/Google related ones."""
    youtube_cookies = {}
    
    for cookie in cookies:
        domain = cookie.get("domain", "").lower()
        name = cookie.get("name", "").lower()
        
        # Include cookies for YouTube domains
        if "youtube.com" in domain or "google.com" in domain:
            youtube_cookies[name] = cookie["value"]
    
    return youtube_cookies


def format_cookies_for_ytmusicapi(cookies: Dict[str, str]) -> Dict[str, str]:
    """Format cookies for ytmusicapi as a headers dict."""
    # ytmusicapi.setup_browser() expects a full headers dict
    # We need to convert our cookies into the proper format
    from ytmusicapi.auth.browser import initialize_headers
    
    # Get default headers
    default_headers = initialize_headers()
    
    # Add our cookies to the headers
    # The cookie header should be a single string with all cookies
    cookie_string = "; ".join([f"{k}={v}" for k, v in cookies.items()])
    default_headers["cookie"] = cookie_string
    
    # Add x-goog-authuser if we have it (from cookies)
    # Usually it's "0" for the first account
    if "x-goog-authuser" not in default_headers:
        default_headers["x-goog-authuser"] = "0"
    
    return dict(default_headers)


def main():
    parser = argparse.ArgumentParser(description="Extract YouTube Music cookies from browser")
    parser.add_argument("--browser", type=str, default="chrome", 
                        choices=["chrome", "chromium", "edge", "brave", "firefox", "safari"],
                        help="Browser to extract cookies from")
    parser.add_argument("--output", type=str, default=None,
                        help="Output file path (default: .amp/cache/cookies.json)")
    parser.add_argument("--format", type=str, default="json",
                        choices=["json", "headers"],
                        help="Output format")
    
    args = parser.parse_args()
    
    print(f"Extracting cookies from {args.browser}...")
    
    cookies = get_cookies_from_browser(args.browser)
    
    if not cookies:
        print("No cookies found. Make sure:")
        print("  1. You're logged in to YouTube Music in your browser")
        print("  2. The browser is closed (cookies are locked while browser is running)")
        return
    
    print(f"Found {len(cookies)} cookies")
    
    youtube_cookies = filter_youtube_cookies(cookies)
    print(f"YouTube-related cookies: {len(youtube_cookies)}")
    
    if not youtube_cookies:
        print("No YouTube cookies found. Please log in to YouTube Music and try again.")
        return
    
    # Print the cookies
    print("\nYouTube Cookies:")
    for name, value in youtube_cookies.items():
        print(f"  {name}: {value[:50]}{'...' if len(value) > 50 else ''}")
    
    # Format for ytmusicapi
    if args.format == "json":
        output_data = youtube_cookies
    else:  # headers format (default for ytmusicapi)
        # Convert to proper headers format
        output_data = format_cookies_for_ytmusicapi(youtube_cookies)
    
    # Determine output path
    output_path = args.output
    if not output_path:
        # Default to .amp/cache/cookies.json relative to script location
        script_dir = Path(__file__).parent
        amp_dir = script_dir.parent.parent / ".amp" / "cache"
        amp_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(amp_dir / "cookies.json")
    
    # Save to file
    try:
        with open(output_path, 'w') as f:
            json.dump(output_data, f, indent=2)
        print(f"\nCookies saved to: {output_path}")
        print("\nYou can now use these cookies with ytmusicapi!")
    except Exception as e:
        print(f"Error saving cookies: {e}")


if __name__ == "__main__":
    main()
