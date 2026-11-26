-- NodeShare PostgreSQL Schema Migration for Supabase
-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- USERS TABLE
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(30) UNIQUE NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    avatar_url TEXT,
    is_teacher BOOLEAN NOT NULL DEFAULT FALSE,
    teacher_verified BOOLEAN NOT NULL DEFAULT FALSE,
    teacher_title VARCHAR(100),
    is_admin BOOLEAN NOT NULL DEFAULT FALSE,
    status_message VARCHAR(255),
    is_online BOOLEAN NOT NULL DEFAULT FALSE,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for Smart User Search (English & Bengali trigram support)
CREATE INDEX IF NOT EXISTS idx_users_username_trgm ON users USING gin (username gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_users_full_name_trgm ON users USING gin (full_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_users_username_lower ON users (LOWER(username));
CREATE INDEX IF NOT EXISTS idx_users_is_teacher ON users (is_teacher, teacher_verified);

-- REFRESH TOKENS (Secure session rotation and revocation)
CREATE TABLE IF NOT EXISTS refresh_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(64) NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked BOOLEAN NOT NULL DEFAULT FALSE,
    replaced_by_token_hash VARCHAR(64),
    user_agent TEXT,
    ip_address VARCHAR(45),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user ON refresh_tokens (user_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_hash ON refresh_tokens (token_hash);

-- FRIEND REQUESTS
CREATE TABLE IF NOT EXISTS friend_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sender_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    receiver_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'rejected', 'cancelled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT no_self_friend_request CHECK (sender_id != receiver_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_pending_friend_request 
ON friend_requests (LEAST(sender_id, receiver_id), GREATEST(sender_id, receiver_id)) 
WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_friend_requests_sender ON friend_requests (sender_id);
CREATE INDEX IF NOT EXISTS idx_friend_requests_receiver ON friend_requests (receiver_id);

-- FRIENDSHIPS (Canonical ordering: user_id < friend_id ensures single row per friendship)
CREATE TABLE IF NOT EXISTS friendships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    friend_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT friendship_ordering CHECK (user_id < friend_id),
    CONSTRAINT uq_friendship UNIQUE (user_id, friend_id)
);

CREATE INDEX IF NOT EXISTS idx_friendships_user ON friendships (user_id);
CREATE INDEX IF NOT EXISTS idx_friendships_friend ON friendships (friend_id);

-- USER BLOCKS
CREATE TABLE IF NOT EXISTS user_blocks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    blocker_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    blocked_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT no_self_block CHECK (blocker_id != blocked_id),
    CONSTRAINT uq_user_block UNIQUE (blocker_id, blocked_id)
);

CREATE INDEX IF NOT EXISTS idx_user_blocks_blocker ON user_blocks (blocker_id);
CREATE INDEX IF NOT EXISTS idx_user_blocks_blocked ON user_blocks (blocked_id);

-- CONVERSATIONS METADATA
CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type VARCHAR(20) NOT NULL CHECK (type IN ('direct', 'group')),
    last_message_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- CONVERSATION PARTICIPANTS
CREATE TABLE IF NOT EXISTS conversation_participants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_read_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_read_message_id VARCHAR(64),
    CONSTRAINT uq_conversation_participant UNIQUE (conversation_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_conv_part_user ON conversation_participants (user_id);
CREATE INDEX IF NOT EXISTS idx_conv_part_conv ON conversation_participants (conversation_id);

-- GROUPS METADATA
CREATE TABLE IF NOT EXISTS groups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE UNIQUE,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    avatar_url TEXT,
    creator_id UUID REFERENCES users(id) ON DELETE SET NULL,
    is_teacher_group BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_groups_creator ON groups (creator_id);

-- GROUP MEMBERS
CREATE TABLE IF NOT EXISTS group_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id UUID NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL DEFAULT 'member' CHECK (role IN ('owner', 'admin', 'member')),
    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_group_member UNIQUE (group_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_group_members_group ON group_members (group_id);
CREATE INDEX IF NOT EXISTS idx_group_members_user ON group_members (user_id);

-- NOTIFICATIONS
CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type VARCHAR(50) NOT NULL,
    title VARCHAR(255) NOT NULL,
    body TEXT NOT NULL,
    data JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_notifications_user_read ON notifications (user_id, is_read, created_at DESC);

-- FILE RECORDS & STORAGE METADATA
CREATE TABLE IF NOT EXISTS file_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    uploader_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    bucket_name VARCHAR(100) NOT NULL DEFAULT 'nodeshare-files',
    file_path TEXT NOT NULL,
    filename VARCHAR(255) NOT NULL,
    mime_type VARCHAR(100) NOT NULL,
    size_bytes BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'completed', 'deleted')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_file_records_uploader ON file_records (uploader_id);
CREATE INDEX IF NOT EXISTS idx_file_records_status ON file_records (status);

-- REALTIME PUBLICATION SETUP FOR SUPABASE
-- Publish notifications and conversations updates to Supabase Realtime
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_publication WHERE pubname = 'supabase_realtime') THEN
        ALTER PUBLICATION supabase_realtime ADD TABLE notifications;
        ALTER PUBLICATION supabase_realtime ADD TABLE conversations;
    END IF;
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;
