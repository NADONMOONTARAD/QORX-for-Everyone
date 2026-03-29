import { Pool, type PoolConfig } from "pg";

/**
 * Centralised Postgres pool.
 *
 * - In development (`npm run dev`) → reads DATABASE_URL from .env (localhost / DBeaver)
 * - On Vercel (production)        → prefers DATABASE_URL_POOLED, then DATABASE_URL
 *
 * No extra toggle needed: Vercel env vars naturally override the local .env.
 */

declare global {
    var __stockAnalysisPool: Pool | undefined;
    var __stockAnalysisPoolWarningShown: boolean | undefined;
}

function isVercelRuntime(): boolean {
    return Boolean(process.env.VERCEL || process.env.VERCEL_ENV);
}

function looksLikePostgresUrl(value: string): boolean {
    return /^postgres(?:ql)?:\/\//i.test(value);
}

function isPlaceholderHost(hostname: string): boolean {
    const host = hostname.toLowerCase();

    return (
        host === "base" ||
        host === "your-pooler-host" ||
        host.endsWith(".example.com")
    );
}

function getDatabaseUrl(): string {
    const vercel = isVercelRuntime();
    const candidates = vercel
        ? ([
              ["DATABASE_URL_POOLED", process.env.DATABASE_URL_POOLED],
              ["DATABASE_URL", process.env.DATABASE_URL],
          ] as const)
        : ([["DATABASE_URL", process.env.DATABASE_URL]] as const);

    const invalidCandidates: string[] = [];

    for (const [name, rawValue] of candidates) {
        const value = rawValue?.trim();
        if (!value) {
            continue;
        }

        if (!looksLikePostgresUrl(value)) {
            invalidCandidates.push(`${name}=not-a-postgres-url`);
            continue;
        }

        const parsed = parseDatabaseUrl(value);
        if (!parsed?.hostname) {
            invalidCandidates.push(`${name}=unparseable`);
            continue;
        }

        if (isPlaceholderHost(parsed.hostname)) {
            invalidCandidates.push(`${name}=placeholder-host:${parsed.hostname}`);
            continue;
        }

        return value;
    }

    const reason =
        invalidCandidates.length > 0
            ? ` Invalid values: ${invalidCandidates.join(", ")}.`
            : "";
    throw new Error(
        vercel
            ? `No valid Postgres connection string is set for Vercel. Set DATABASE_URL_POOLED to your Supabase pooled connection string.${reason}`
            : `No valid Postgres connection string is set for local development. Set DATABASE_URL to your local Postgres instance.${reason}`,
    );
}

function parseDatabaseUrl(url: string): URL | null {
    try {
        return new URL(url);
    } catch {
        return null;
    }
}

function shouldUseSsl(url: string, parsed: URL | null): PoolConfig["ssl"] {
    const host = parsed?.hostname.toLowerCase();
    const sslMode = parsed?.searchParams.get("sslmode")?.toLowerCase();
    const isLocalHost = host === "localhost" || host === "127.0.0.1";

    if (isLocalHost || sslMode === "disable") {
        return undefined;
    }

    if (
        sslMode === "require" ||
        url.includes("supabase.co") ||
        url.includes("supabase.com") ||
        url.includes("neon.tech")
    ) {
        return { rejectUnauthorized: false };
    }

    return undefined;
}

function isSupabaseSessionMode(parsed: URL | null): boolean {
    return (
        parsed?.hostname.toLowerCase().includes("pooler.supabase.com") === true &&
        parsed.port === "5432"
    );
}

function resolvePoolMax(parsed: URL | null): number {
    const explicitMax = Number.parseInt(process.env.PG_POOL_MAX ?? "", 10);
    if (Number.isInteger(explicitMax) && explicitMax > 0) {
        return explicitMax;
    }

    if (isSupabaseSessionMode(parsed)) {
        return 1;
    }

    return process.env.VERCEL ? 1 : 5;
}

function warnIfSessionMode(parsed: URL | null): void {
    if (!isSupabaseSessionMode(parsed) || globalThis.__stockAnalysisPoolWarningShown) {
        return;
    }

    console.warn(
        "[db] Supabase Session mode detected. On Vercel, switch to the pooled Transaction mode URL and store it in DATABASE_URL_POOLED to avoid MaxClientsInSessionMode errors.",
    );
    globalThis.__stockAnalysisPoolWarningShown = true;
}

const buildPoolConfig = (): PoolConfig => {
    const url = getDatabaseUrl();
    const parsed = parseDatabaseUrl(url);

    warnIfSessionMode(parsed);

    return {
        connectionString: url,
        ssl: shouldUseSsl(url, parsed),
        max: resolvePoolMax(parsed),
        idleTimeoutMillis: 10_000,
        connectionTimeoutMillis: 10_000,
        allowExitOnIdle: true,
    };
};

export function getPool(): Pool {
    if (!globalThis.__stockAnalysisPool) {
        globalThis.__stockAnalysisPool = new Pool(buildPoolConfig());
    }

    return globalThis.__stockAnalysisPool;
}
