-- Shared primary-only coordinator for GET /api/firmware/{id}/popularity/live.
-- Apply once to the provisioned Postgres primary before setting POPULARITY_DATABASE_URL.
-- The singleton row is mandatory: the endpoint refuses to fetch if it is absent.
CREATE TABLE IF NOT EXISTS popularity_refresh_budget (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    hour_start timestamptz NOT NULL,
    used integer NOT NULL DEFAULT 0 CHECK (used >= 0 AND used <= 20),
    lease_token text,
    lease_until timestamptz,
    cooldown_until timestamptz
);

INSERT INTO popularity_refresh_budget (singleton, hour_start, used)
VALUES (true, date_trunc('hour', clock_timestamp() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC', 0)
ON CONFLICT (singleton) DO NOTHING;

CREATE TABLE IF NOT EXISTS popularity_refresh_repo (
    repo_id bigint PRIMARY KEY CHECK (repo_id > 0),
    full_name text NOT NULL,
    stars bigint CHECK (stars >= 0),
    forks bigint CHECK (forks >= 0),
    observed_at timestamptz,
    lease_token text,
    lease_until timestamptz,
    retry_after timestamptz,
    CHECK ((stars IS NULL AND forks IS NULL AND observed_at IS NULL) OR
           (stars IS NOT NULL AND forks IS NOT NULL AND observed_at IS NOT NULL))
);
