-- Row Level Security (RLS) Policies for NodeShare
-- These ensure security in Supabase when querying directly via client or service

ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE refresh_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE friend_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE friendships ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_blocks ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversation_participants ENABLE ROW LEVEL SECURITY;
ALTER TABLE groups ENABLE ROW LEVEL SECURITY;
ALTER TABLE group_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE file_records ENABLE ROW LEVEL SECURITY;

-- Service Role Key bypasses RLS automatically.
-- The backend uses PostgreSQL direct connection via asyncpg with database credentials 
-- or Supabase service_role key to enforce server-side business rules.

-- Sample client-side read policies if client queries directly with Supabase JWT:
CREATE POLICY "Public user profiles are viewable by authenticated users"
ON users FOR SELECT
USING (auth.role() = 'authenticated');

CREATE POLICY "Users can view their own refresh tokens"
ON refresh_tokens FOR SELECT
USING (auth.uid() = user_id);

CREATE POLICY "Users can view their own notifications"
ON notifications FOR ALL
USING (auth.uid() = user_id);

CREATE POLICY "Users can view friendships they belong to"
ON friendships FOR SELECT
USING (auth.uid() = user_id OR auth.uid() = friend_id);

CREATE POLICY "Users can view conversation participants if they belong to it"
ON conversation_participants FOR SELECT
USING (
    EXISTS (
        SELECT 1 FROM conversation_participants cp 
        WHERE cp.conversation_id = conversation_participants.conversation_id 
        AND cp.user_id = auth.uid()
    )
);

CREATE POLICY "Users can view groups they are member of"
ON groups FOR SELECT
USING (
    EXISTS (
        SELECT 1 FROM group_members gm 
        WHERE gm.group_id = groups.id 
        AND gm.user_id = auth.uid()
    )
);
