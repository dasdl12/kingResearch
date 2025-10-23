-- 修复历史记录的 user_id
-- 这个脚本会将所有 user_id 为 NULL 的已完成研究关联到指定用户

-- 1. 首先查看您的用户 ID
SELECT id, username, email, display_name FROM users;

-- 2. 查看需要修复的研究记录
SELECT thread_id, research_topic, completed_at, user_id 
FROM research_replays 
WHERE is_completed = TRUE AND user_id IS NULL
ORDER BY completed_at DESC;

-- 3. 修复记录（请将 'YOUR_USERNAME' 替换为您实际的用户名）
-- 如果您的用户名是 admin，就替换成 'admin'
UPDATE research_replays 
SET user_id = (SELECT id FROM users WHERE username = 'YOUR_USERNAME' LIMIT 1)
WHERE is_completed = TRUE AND user_id IS NULL;

-- 4. 验证修复结果
SELECT thread_id, research_topic, user_id, completed_at 
FROM research_replays 
WHERE is_completed = TRUE
ORDER BY completed_at DESC
LIMIT 10;





