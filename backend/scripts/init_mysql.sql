-- Relayvia MySQL 初始化脚本（在腾讯云 MySQL 上用管理员账号执行）
-- 注意：将 CHANGE_ME_STRONG_PASSWORD 替换为强密码，并同步到 .env 的 RELAYVIA_DATABASE_URL。

CREATE DATABASE IF NOT EXISTS relayvia
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_0900_ai_ci;

CREATE USER IF NOT EXISTS 'relayvia'@'%' IDENTIFIED BY 'CHANGE_ME_STRONG_PASSWORD';

-- 仅授予 relayvia 库权限（Alembic migration 需要建表/改表权限）
GRANT ALL PRIVILEGES ON relayvia.* TO 'relayvia'@'%';

FLUSH PRIVILEGES;
