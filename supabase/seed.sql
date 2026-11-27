-- NodeShare Seed Data for Development
-- Passwords are hashed with Argon2id for password: "Password123!"
-- Hash: $argon2id$v=19$m=65536,t=3,p=4$a47caMC+dLCUOfu+XMRUxw$IilrDuIl0/LkGIYbX4cDI83NlCgA5JUiRnb4rZgspUg

-- Insert Admin User
INSERT INTO users (id, username, full_name, password_hash, is_teacher, teacher_verified, is_admin, status_message)
VALUES (
    '00000000-0000-0000-0000-000000000001',
    'admin',
    'System Administrator',
    '$argon2id$v=19$m=65536,t=3,p=4$a47caMC+dLCUOfu+XMRUxw$IilrDuIl0/LkGIYbX4cDI83NlCgA5JUiRnb4rZgspUg',
    FALSE,
    FALSE,
    TRUE,
    'NodeShare Administrator'
) ON CONFLICT (username) DO NOTHING;

-- Insert Verified Teacher
INSERT INTO users (id, username, full_name, password_hash, is_teacher, teacher_verified, teacher_title, is_admin, status_message)
VALUES (
    '00000000-0000-0000-0000-000000000002',
    'prof_rahim',
    'Abdur Rahim (আব্দুর রহিম)',
    '$argon2id$v=19$m=65536,t=3,p=4$a47caMC+dLCUOfu+XMRUxw$IilrDuIl0/LkGIYbX4cDI83NlCgA5JUiRnb4rZgspUg',
    TRUE,
    TRUE,
    'Assistant Professor of Computer Science',
    FALSE,
    'Available for consultation Sun-Thu 10am-2pm'
) ON CONFLICT (username) DO NOTHING;

-- Insert Regular User 1 (English + Bengali name for smart search test)
INSERT INTO users (id, username, full_name, password_hash, is_teacher, teacher_verified, is_admin, status_message)
VALUES (
    '00000000-0000-0000-0000-000000000003',
    'prantik',
    'Prantik Das (প্রান্তিক দাস)',
    '$argon2id$v=19$m=65536,t=3,p=4$a47caMC+dLCUOfu+XMRUxw$IilrDuIl0/LkGIYbX4cDI83NlCgA5JUiRnb4rZgspUg',
    FALSE,
    FALSE,
    FALSE,
    'Building NodeShare on Windows'
) ON CONFLICT (username) DO NOTHING;

-- Insert Regular User 2
INSERT INTO users (id, username, full_name, password_hash, is_teacher, teacher_verified, is_admin, status_message)
VALUES (
    '00000000-0000-0000-0000-000000000004',
    'tanvir',
    'Tanvir Ahmed',
    '$argon2id$v=19$m=65536,t=3,p=4$a47caMC+dLCUOfu+XMRUxw$IilrDuIl0/LkGIYbX4cDI83NlCgA5JUiRnb4rZgspUg',
    FALSE,
    FALSE,
    FALSE,
    'NodeShare beta tester'
) ON CONFLICT (username) DO NOTHING;
