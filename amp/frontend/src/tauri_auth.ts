/**
 * Tauri-specific auth functions for YouTube Music sign-in.
 * Uses Tauri's webview to open a sign-in window and read cookies directly.
 */

// Type for cookies returned from Tauri
export interface TauriCookie {
  name: string;
  value: string;
  domain?: string;
}

// Lazy import of invoke to avoid issues when not in Tauri
let invokeFn: ((command: string, ...args: any[]) => Promise<any>) | null = null;
let isAvailableCache: boolean | null = null;

async function getInvoke(): Promise<((command: string, ...args: any[]) => Promise<any>) | null> {
  if (invokeFn !== null) {
    return invokeFn;
  }
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    invokeFn = invoke;
    isAvailableCache = true;
    return invoke;
  } catch {
    isAvailableCache = false;
    return null;
  }
}

/**
 * Open a YouTube Music sign-in window in Tauri webview.
 * The user signs in normally, and Tauri reads the cookies from the webview.
 * Returns the cookies or throws an error if cancelled/timeout.
 */
export async function youtubeLogin(): Promise<TauriCookie[]> {
  const invoke = await getInvoke();
  if (!invoke) {
    throw new Error("Tauri is not available. Please run the app via 'npm run tauri dev' or as a built Tauri app.");
  }
  
  try {
    const cookies: TauriCookie[] = await invoke("youtube_login");
    return cookies;
  } catch (error) {
    const errorString = String(error);
    if (errorString.includes("cancelled")) {
      throw new Error("Sign-in was cancelled by the user");
    } else if (errorString.includes("timeout")) {
      throw new Error("Sign-in timed out after 10 minutes");
    }
    throw new Error(`Sign-in failed: ${errorString}`);
  }
}

/**
 * Check if Tauri is available (running in a Tauri app).
 */
export async function isTauriAvailable(): Promise<boolean> {
  if (isAvailableCache !== null) {
    return isAvailableCache;
  }
  const invoke = await getInvoke();
  return invoke !== null;
}

/**
 * Synchronous check if Tauri might be available (for UI rendering).
 * This is a best-effort check that doesn't throw.
 */
export function mightBeTauri(): boolean {
  // If we already determined it, return cached value
  if (isAvailableCache !== null) {
    return isAvailableCache;
  }
  // Check if @tauri-apps/api is likely to be available
  // This is a heuristic - in a real Tauri app, the import will work
  return typeof window !== "undefined";
}
