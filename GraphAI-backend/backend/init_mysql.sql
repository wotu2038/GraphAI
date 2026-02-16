-- ============================================================
-- MySQL 数据库初始化脚本
-- ============================================================
-- 
-- 【重要说明】
-- 此脚本由 docker-compose 在 MySQL 容器首次启动时自动执行。
-- 数据库名和用户名通过 docker-compose.backend.yml 的环境变量配置：
--   - MYSQL_DATABASE: 数据库名（从 .env 读取，默认 graph_ai）
--   - MYSQL_USER: 数据库用户（从 .env 读取，默认 graph_ai）
-- 
-- 注意：
-- 1. MySQL 的 MYSQL_DATABASE 环境变量会在首次初始化时自动创建数据库
-- 2. 此脚本确保数据库存在（如果环境变量创建失败时的备用方案）
-- 3. 表结构由 SQLAlchemy 在应用启动时通过 init_db() 自动创建
-- 4. 数据持久化：数据存储在 mysql_data 卷中，重启容器不会丢失数据
-- 
-- 如果数据库被删除，可能是以下原因：
-- - 执行了 docker-compose down -v（删除了数据卷）
-- - 手动删除了数据卷
-- - MySQL 容器重新初始化（数据目录为空）
-- ============================================================

-- 设置字符集（对后续创建的表生效）
SET NAMES utf8mb4;
SET CHARACTER_SET_CLIENT = utf8mb4;
SET CHARACTER_SET_RESULTS = utf8mb4;
SET COLLATION_CONNECTION = utf8mb4_unicode_ci;

-- 确保数据库存在（备用方案，通常由 MYSQL_DATABASE 环境变量自动创建）
-- 注意：这里使用变量 ${MYSQL_DATABASE}，但 SQL 脚本中无法直接使用环境变量
-- 实际数据库创建由 MySQL 容器的 MYSQL_DATABASE 环境变量处理
