#!/bin/bash
# =============================================================================
# 数据库备份脚本
# 每天自动执行，备份 SQLite 数据库到 /var/backups 并推送到 GitHub
# =============================================================================

set -e

APP_DIR="/var/www/email_automation"
DB_PATH="${APP_DIR}/database/email_automation.db"
BACKUP_DIR="/var/backups/email_automation"
GITHUB_BACKUP_REPO="${GITHUB_BACKUP_REPO:-}"
RETENTION_DAYS=30

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="email_automation_${DATE}.db"

mkdir -p "${BACKUP_DIR}"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] 开始备份数据库..."

# 检查数据库文件是否存在
if [ ! -f "${DB_PATH}" ]; then
    echo "  ✗ 数据库文件不存在: ${DB_PATH}"
    exit 1
fi

# 使用 SQLite 的 .backup 命令进行热备份（避免 WAL 锁竞争）
sqlite3 "${DB_PATH}" ".backup '${BACKUP_DIR}/${BACKUP_FILE}'"

echo "  ✓ 备份完成: ${BACKUP_DIR}/${BACKUP_FILE}"
echo "  大小: $(du -h ${BACKUP_DIR}/${BACKUP_FILE} | cut -f1)"

# 清理旧备份（保留 RETENTION_DAYS 天）
echo "  清理 ${RETENTION_DAYS} 天前的旧备份..."
find "${BACKUP_DIR}" -name "email_automation_*.db" -mtime +${RETENTION_DAYS} -delete

# 可选：推送到 GitHub 备份仓库
if [ -n "${GITHUB_BACKUP_REPO}" ]; then
    GITHUB_BACKUP_DIR="/var/backups/email_automation_github"

    if [ ! -d "${GITHUB_BACKUP_DIR}/.git" ]; then
        echo "  初始化 GitHub 备份仓库..."
        mkdir -p "${GITHUB_BACKUP_DIR}"
        cd "${GITHUB_BACKUP_DIR}"
        git init
        git remote add origin "${GITHUB_BACKUP_REPO}"
        git lfs track "*.db" 2>/dev/null || true
    fi

    cd "${GITHUB_BACKUP_DIR}"
    cp "${BACKUP_DIR}/${BACKUP_FILE}" .
    git add .
    git commit -m "Database backup ${DATE}" || true
    git push origin main || true
    echo "  ✓ 已推送到 GitHub"
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] 备份任务完成"
