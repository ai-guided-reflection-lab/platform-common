-- Shared across workers; a launch nonce can be accepted only once per consumer.
CREATE TABLE lti11_nonces_platform (
    nonce_hash TEXT PRIMARY KEY,
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX lti11_nonces_expiry ON lti11_nonces_platform (expires_at);
