-- =============================================
-- PostgreSQL Init Script
-- Runs automatically when container starts fresh
-- =============================================

-- Create incidents table
-- Stores every network incident diagnosed by the AI Agent
CREATE TABLE IF NOT EXISTS incidents (
    id              SERIAL PRIMARY KEY,
    alert_id        VARCHAR(36) NOT NULL UNIQUE,     -- UUID from alert
    device_id       VARCHAR(10) NOT NULL,            -- e.g. "R1", "S2"
    alert_type      VARCHAR(50) NOT NULL,            -- e.g. "HIGH_LATENCY"
    severity        VARCHAR(20) NOT NULL,            -- INFO | WARNING | CRITICAL | EMERGENCY
    root_cause      TEXT,                            -- AI-determined root cause
    confidence_score FLOAT,                          -- AI confidence 0.0 to 1.0
    recommendation  TEXT,                            -- AI recommended fix
    jira_ticket_id  VARCHAR(20),                     -- e.g. "NET-1042"
    resolved        BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    resolved_at     TIMESTAMP WITH TIME ZONE,
    raw_alert       JSONB                            -- Full alert payload for audit
);

-- Create devices table
-- Registry of all network devices in the system
CREATE TABLE IF NOT EXISTS devices (
    device_id       VARCHAR(10) PRIMARY KEY,        -- e.g. "R1", "S2", "AP1"
    device_type     VARCHAR(20) NOT NULL,           -- ROUTER | SWITCH | ACCESS_POINT
    location        VARCHAR(100),                   -- e.g. "DataCenter-A"
    ip_address      VARCHAR(15),
    neighbors       TEXT[],                         -- Array of neighboring device IDs
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create agent_actions table
-- Audit log of every action the AI Agent took
CREATE TABLE IF NOT EXISTS agent_actions (
    id              SERIAL PRIMARY KEY,
    incident_id     INTEGER REFERENCES incidents(id),
    action_type     VARCHAR(50) NOT NULL,           -- CREATE_TICKET | NOTIFY | LOG
    action_payload  JSONB,                          -- Full action data
    success         BOOLEAN DEFAULT TRUE,
    error_message   TEXT,
    executed_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_incidents_device_id ON incidents(device_id);
CREATE INDEX IF NOT EXISTS idx_incidents_severity ON incidents(severity);
CREATE INDEX IF NOT EXISTS idx_incidents_created_at ON incidents(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_incidents_resolved ON incidents(resolved);
CREATE INDEX IF NOT EXISTS idx_agent_actions_incident ON agent_actions(incident_id);

-- Insert initial device registry
INSERT INTO devices (device_id, device_type, location, ip_address, neighbors) VALUES
    ('R1',  'ROUTER',        'DataCenter-Core',      '192.168.1.1',  ARRAY['R2', 'R3', 'S1', 'S2']),
    ('R2',  'ROUTER',        'DataCenter-Core',      '192.168.1.2',  ARRAY['R1', 'R3', 'S3', 'S4']),
    ('R3',  'ROUTER',        'DataCenter-Edge',      '192.168.1.3',  ARRAY['R1', 'R2']),
    ('S1',  'SWITCH',        'Floor-1-Distribution', '192.168.2.1',  ARRAY['R1', 'AP1']),
    ('S2',  'SWITCH',        'Floor-2-Distribution', '192.168.2.2',  ARRAY['R1', 'AP2']),
    ('S3',  'SWITCH',        'Floor-3-Distribution', '192.168.2.3',  ARRAY['R2', 'AP3']),
    ('S4',  'SWITCH',        'DataCenter-Access',    '192.168.2.4',  ARRAY['R2']),
    ('AP1', 'ACCESS_POINT',  'Floor-1-Zone-A',       '192.168.3.1',  ARRAY['S1']),
    ('AP2', 'ACCESS_POINT',  'Floor-2-Zone-A',       '192.168.3.2',  ARRAY['S2']),
    ('AP3', 'ACCESS_POINT',  'Floor-3-Zone-A',       '192.168.3.3',  ARRAY['S3'])
ON CONFLICT (device_id) DO NOTHING;
