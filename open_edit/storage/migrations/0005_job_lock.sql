CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_one_running ON jobs(status) WHERE status = 'running';
