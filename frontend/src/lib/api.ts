/**
 * Shared API helper for the frontend.
 *
 * All calls now go to the Next.js internal API routes (same origin),
 * which in turn query the database directly.
 * No external Python backend is needed.
 */

export const callApi = async (path: string, init?: RequestInit) => {
    const url = path.startsWith("http") ? path : path;
    const res = await fetch(url, {
        ...init,
    });
    if (!res.ok) {
        throw new Error(`HTTP ${res.status} at ${url}`);
    }
    return res;
};
