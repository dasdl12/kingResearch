-- Migration: Add user authentication and associate conversations with users
-- Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
-- SPDX-License-Identifier: MIT

-- ============================================================
-- 1. Create users table
-- ============================================================

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    display_name VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE,
    
    -- Simple quota control
    daily_quota INTEGER DEFAULT 10,  -- Researches allowed per day
    used_today INTEGER DEFAULT 0,
    last_reset_date DATE DEFAULT CURRENT_DATE
);

-- Create indexes for users table
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_is_active ON users(is_active);

-- ============================================================
-- 2. Modify existing tables to add user_id
-- ============================================================

-- Add user_id to research_replays if not exists
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'research_replays' AND column_name = 'user_id'
    ) THEN
        ALTER TABLE research_replays 
            ADD COLUMN user_id UUID REFERENCES users(id) ON DELETE CASCADE;
    END IF;
END $$;

-- Add is_completed flag to track finished reports
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'research_replays' AND column_name = 'is_completed'
    ) THEN
        ALTER TABLE research_replays 
            ADD COLUMN is_completed BOOLEAN DEFAULT FALSE;
    END IF;
END $$;

-- Add final_report column to store the completed report
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'research_replays' AND column_name = 'final_report'
    ) THEN
        ALTER TABLE research_replays 
            ADD COLUMN final_report TEXT;
    END IF;
END $$;

-- Add observations column to store research process activities
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'research_replays' AND column_name = 'observations'
    ) THEN
        ALTER TABLE research_replays 
            ADD COLUMN observations JSONB;
    END IF;
END $$;

-- Add plan column to store research plan
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'research_replays' AND column_name = 'plan'
    ) THEN
        ALTER TABLE research_replays 
            ADD COLUMN plan JSONB;
    END IF;
END $$;

-- Add completed_at column to track completion time
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'research_replays' AND column_name = 'completed_at'
    ) THEN
        ALTER TABLE research_replays 
            ADD COLUMN completed_at TIMESTAMP WITH TIME ZONE;
    END IF;
END $$;

-- Create indexes for research_replays
CREATE INDEX IF NOT EXISTS idx_research_replays_user_id ON research_replays(user_id);
CREATE INDEX IF NOT EXISTS idx_research_replays_user_thread ON research_replays(user_id, thread_id);
CREATE INDEX IF NOT EXISTS idx_research_replays_is_completed ON research_replays(is_completed);

-- Add user_id to langgraph_events if exists
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'langgraph_events') THEN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'langgraph_events' AND column_name = 'user_id'
        ) THEN
            ALTER TABLE langgraph_events 
                ADD COLUMN user_id UUID REFERENCES users(id) ON DELETE CASCADE;
            
            CREATE INDEX IF NOT EXISTS idx_langgraph_events_user_id ON langgraph_events(user_id);
        END IF;
    END IF;
END $$;

-- Add user_id to chat_streams if exists
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'chat_streams') THEN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'chat_streams' AND column_name = 'user_id'
        ) THEN
            ALTER TABLE chat_streams 
                ADD COLUMN user_id UUID REFERENCES users(id) ON DELETE CASCADE;
            
            CREATE INDEX IF NOT EXISTS idx_chat_streams_user_id ON chat_streams(user_id);
        END IF;
    END IF;
END $$;

-- ============================================================
-- 3. Create sessions table (optional, for token management)
-- ============================================================

CREATE TABLE IF NOT EXISTS sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(255) NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    user_agent TEXT,
    ip_address INET
);

CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_token_hash ON sessions(token_hash);
CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at);

-- ============================================================
-- 4. Create a demo user (optional, for testing)
-- ============================================================

-- Uncomment the following to create a demo user
-- Password: demo123456 (bcrypt hash)
/*
INSERT INTO users (username, email, password_hash, display_name, daily_quota)
VALUES (
    'demo',
    'demo@example.com',
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LeGviO.X.lCHWOQmW',
    'Demo User',
    100
) ON CONFLICT (username) DO NOTHING;
*/

