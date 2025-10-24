-- ============================================================
-- 安全诊断 SQL：检查为什么前端看不到历史记录
-- 说明：已加 LIMIT、只取轻量字段、避免加载大字段
-- ============================================================

-- 0️⃣ 查看表结构（可确认有哪些字段，不触发崩溃）
\d public.research_replays;

-- ============================================================
-- 1️⃣ 抽查看当前用户的研究记录，大约 10 条
-- ============================================================
SELECT 
    thread_id,
    COALESCE(research_topic, '[NULL]') AS research_topic,
    is_completed,
    completed_at,
    created_at,
    ts,
    LENGTH(COALESCE(final_report, '')) AS report_length
FROM public.research_replays
WHERE user_id = 'addad6af-ad2e-4683-8e57-1fa2f173e213'
ORDER BY ts DESC
LIMIT 10;

-- ============================================================
-- 2️⃣ 检查 completed_at 是否为空（取少量行）
-- ============================================================
SELECT 
    thread_id,
    is_completed,
    completed_at IS NULL AS completed_at_is_null,
    completed_at
FROM public.research_replays
WHERE user_id = 'addad6af-ad2e-4683-8e57-1fa2f173e213'
ORDER BY ts DESC
LIMIT 10;

-- ============================================================
-- 3️⃣ 模拟前端实际查询 (分页限制)
-- ============================================================
SELECT 
    id, 
    thread_id, 
    is_completed, 
    completed_at
FROM public.research_replays
WHERE user_id = 'addad6af-ad2e-4683-8e57-1fa2f173e213'
  AND is_completed = TRUE
ORDER BY completed_at DESC
LIMIT 5;
-- ============================================================
-- 4️⃣ 若 confirmed 某些行完成但 completed_at 为 NULL，可修复
-- 只处理小批量记录 (LIMIT 50)
-- ============================================================
UPDATE public.research_replays
SET 
    completed_at = COALESCE(completed_at, ts, NOW()),
    ts = NOW()
WHERE user_id = 'addad6af-ad2e-4683-8e57-1fa2f173e213'
  AND is_completed = TRUE
  AND completed_at IS NULL
LIMIT 50;

-- ⚠️ 注意：LIMIT 在 UPDATE 中某些版本无效，如不支持可通过条件控制：
-- 例如 WHERE id IN (SELECT id FROM ... LIMIT 50);

-- ============================================================
-- 5️⃣ 再次验证修复结果
-- ============================================================
SELECT 
    thread_id, 
    COALESCE(research_topic, '[NULL]') AS research_topic, 
    is_completed,
    completed_at,
    ts
FROM public.research_replays
WHERE user_id = 'addad6af-ad2e-4683-8e57-1fa2f173e213'
  AND is_completed = TRUE
ORDER BY COALESCE(completed_at, ts) DESC
LIMIT 10;