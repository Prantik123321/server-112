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

DROP POLICY IF EXISTS "Public user profiles are viewable by authenticated users" ON users;
DROP POLICY IF EXISTS "Users can view their own refresh tokens" ON refresh_tokens;
DROP POLICY IF EXISTS "Users can view their own notifications" ON notifications;
DROP POLICY IF EXISTS "Users can view friendships they belong to" ON friendships;
DROP POLICY IF EXISTS "Users can view conversation participants if they belong to it" ON conversation_participants;
DROP POLICY IF EXISTS "Users can view groups they are member of" ON groups;
DROP POLICY IF EXISTS "Users can view group members in their groups" ON group_members;

-- Service Role Key bypasses RLS automatically.
-- The backend uses PostgreSQL direct connection via asyncpg with database credentials 
-- or Supabase service_role key to enforce server-side business rules.

-- Never expose password_hash or administrative flags to Supabase client roles.
REVOKE ALL ON TABLE public.users FROM PUBLIC, anon, authenticated;
GRANT SELECT (
    id, username, full_name, avatar_url, is_teacher, teacher_verified,
    teacher_title, status_message, is_online, last_seen_at, created_at
) ON TABLE public.users TO authenticated;

CREATE POLICY "Authenticated users can view public profile columns"
ON users FOR SELECT
USING (auth.role() = 'authenticated');

-- Refresh-token hashes and session metadata are accessible only to the backend.
REVOKE ALL ON TABLE public.refresh_tokens FROM PUBLIC, anon, authenticated;

-- Clients may read their notifications; all writes go through the backend.
REVOKE ALL ON TABLE public.notifications FROM PUBLIC, anon, authenticated;
GRANT SELECT ON TABLE public.notifications TO authenticated;

CREATE POLICY "Users can read their own notifications"
ON notifications FOR SELECT
USING (auth.uid() = user_id);

CREATE POLICY "Users can view friendships they belong to"
ON friendships FOR SELECT
USING (auth.uid() = user_id OR auth.uid() = friend_id);

CREATE OR REPLACE FUNCTION public.is_conversation_member(target_conversation_id uuid)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
    SELECT EXISTS (
        SELECT 1
        FROM public.conversation_participants
        WHERE conversation_id = target_conversation_id
          AND user_id = auth.uid()
    )
$$;

CREATE OR REPLACE FUNCTION public.is_group_member(target_group_id uuid)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
    SELECT EXISTS (
        SELECT 1
        FROM public.group_members
        WHERE group_id = target_group_id
          AND user_id = auth.uid()
    )
$$;

REVOKE ALL ON FUNCTION public.is_conversation_member(uuid) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION public.is_group_member(uuid) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.is_conversation_member(uuid) TO authenticated;
GRANT EXECUTE ON FUNCTION public.is_group_member(uuid) TO authenticated;

CREATE POLICY "Users can view conversation participants if they belong to it"
ON conversation_participants FOR SELECT
USING (public.is_conversation_member(conversation_id));

CREATE POLICY "Users can view groups they are member of"
ON groups FOR SELECT
USING (public.is_group_member(id));

CREATE POLICY "Users can view group members in their groups"
ON group_members FOR SELECT
USING (public.is_group_member(group_id));
