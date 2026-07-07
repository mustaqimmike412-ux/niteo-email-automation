# 网站上线部署指南

## 第一步：创建 GitHub 仓库并推送代码

### 1.1 在 GitHub 创建 Private 仓库

1. 登录 [github.com](https://github.com)
2. 点击右上角 `+` → `New repository`
3. Repository name: `niteo-email-automation`（或你喜欢的名字）
4. 选择 **Private**（重要！代码含配置信息）
5. 不要勾选 "Initialize this repository with a README"
6. 点击 `Create repository`

### 1.2 推送本地代码到 GitHub

在本地项目目录下执行：

```bash
cd email_automation

# 添加远程仓库地址（替换为你的用户名）
git remote add origin https://github.com/你的用户名/niteo-email-automation.git

# 推送代码
git push -u origin main
```

输入你的 GitHub 用户名和个人访问令牌（Password 处输入 Token，不是登录密码）。

> 如果没有 Token，在 GitHub 设置 → Developer settings → Personal access tokens → Tokens (classic) → Generate new token，勾选 `repo` 权限。

---

## 第二步：购买域名

### 推荐：Cloudflare Registrar

1. 注册 [cloudflare.com](https://cloudflare.com) 账号
2. 进入 `Registrar` → `Register domains`
3. 搜索域名（如 `niteo-mail.com` / `niteosolar.app`）
4. 按年付费购买（~$10-14/年）
5. Whois 隐私保护免费开启

---

## 第三步：购买 VPS 服务器

### 推荐：Vultr

1. 注册 [vultr.com](https://vultr.com) 账号
2. 点击 `Deploy` → `Deploy New Server`
3. 选择配置：
   - **Cloud Compute (Shared CPU)**
   - **Location**: Singapore / Los Angeles / Tokyo
   - **OS**: Ubuntu 22.04 LTS
   - **Plan**: 1 vCPU / 1GB RAM / 25GB SSD ($5/月)
   - **IPv6**: 可选
4. 点击 `Deploy Now`
5. 等待 1-2 分钟，记录服务器的 **IP 地址** 和 **root 密码**

---

## 第四步：配置 DNS

在 Cloudflare 域名管理页面：

1. 点击你的域名
2. 进入 `DNS` → `Records`
3. 添加 A 记录：
   - Type: `A`
   - Name: `@`（根域名）
   - IPv4 address: `你的VPS IP`
   - Proxy status: 先关闭（灰色云），部署完成后再开启
4. 添加 A 记录：
   - Type: `A`
   - Name: `www`
   - IPv4 address: `你的VPS IP`

---

## 第五步：一键部署

### 5.1 SSH 登录服务器

```bash
ssh root@你的VPS-IP
```

### 5.2 下载并运行部署脚本

```bash
# 设置环境变量（替换为你的域名和GitHub仓库）
export DOMAIN="你的域名.com"
export GITHUB_REPO="https://github.com/你的用户名/niteo-email-automation.git"

# 下载部署脚本
curl -fsSL https://raw.githubusercontent.com/你的用户名/niteo-email-automation/main/deploy/deploy.sh -o /tmp/deploy.sh
chmod +x /tmp/deploy.sh

# 运行部署
/tmp/deploy.sh
```

> 如果 GitHub 文件还没推送，可以手动复制 `deploy/deploy.sh` 内容到服务器执行。

### 5.3 配置环境变量（重要！）

编辑 systemd 服务文件，添加密码等敏感信息：

```bash
nano /etc/systemd/system/email-automation.service
```

在 `[Service]` 段添加：

```ini
Environment="SMTP_PASSWORD=你的SMTP密码"
Environment="IMAP_PASSWORD=你的IMAP密码"
Environment="SECRET_KEY=随机生成的密钥"
Environment="SENDER_EMAIL=travis@niteowork.com"
```

保存后重载并重启：

```bash
systemctl daemon-reload
systemctl restart email-automation
```

### 5.4 配置 GeoIP2 License Key

1. 访问 [MaxMind 注册](https://www.maxmind.com/en/geolite2/signup) 获取免费 License Key
2. 编辑 `/etc/GeoIP.conf`，填入 AccountID 和 LicenseKey
3. 执行 `geoipupdate`
4. 重启 Nginx: `systemctl restart nginx`

---

## 第六步：配置 Cloudflare 防火墙（限制国内访问）

1. 在 Cloudflare 域名页面，进入 `Security` → `WAF` → `Firewall rules`
2. 点击 `Create firewall rule`
3. Rule name: `Block China`
4. Expression: `(ip.geoip.country eq "CN")`
5. Action: `Block`
6. 点击 `Deploy`

然后开启 CDN 代理：
- 回到 `DNS` → `Records`
- 将 A 记录的 Proxy status 改为开启（橙色云）

---

## 第七步：验证部署

### 7.1 检查服务状态

```bash
# 查看应用状态
systemctl status email-automation

# 查看应用日志
journalctl -u email-automation -f

# 查看 Nginx 日志
tail -f /var/log/nginx/access.log
```

### 7.2 测试访问

- 国外访问：`https://你的域名.com` → 应该正常显示仪表盘
- 国内访问：被 Cloudflare 或 Nginx 拦截，返回 403

### 7.3 测试退信检查

```bash
# 手动触发退信检查
curl -X POST https://你的域名.com/api/bounces/check \
  -H "X-Requested-With: XMLHttpRequest"
```

---

## 第八步：设置数据库自动备份

### 8.1 配置备份脚本

编辑 `deploy/backup.sh` 中的 `GITHUB_BACKUP_REPO` 变量（可选，如果你想把备份推送到单独的 GitHub 仓库）。

### 8.2 添加定时任务

```bash
crontab -e
```

添加以下行：

```
# 每天凌晨 3 点备份数据库
0 3 * * * /var/www/email_automation/deploy/backup.sh >> /var/log/backup.log 2>&1

# 每周一清理旧备份
0 4 * * 1 find /var/backups/email_automation -name "email_automation_*.db" -mtime +30 -delete
```

---

## 常见问题

### Q: 部署后无法访问？

1. 检查防火墙：`ufw status`，确保 80/443 端口开放
2. 检查 Nginx：`nginx -t` 测试配置
3. 检查服务：`systemctl status email-automation`
4. 检查日志：`journalctl -u email-automation -n 50`

### Q: 如何更新代码？

```bash
ssh root@你的VPS-IP
cd /var/www/email_automation
git pull origin main
systemctl restart email-automation
```

### Q: 数据库丢失了怎么办？

备份文件位于 `/var/backups/email_automation/`，找到最近的一份备份复制回 `/var/www/email_automation/database/email_automation.db` 即可。

### Q: 国内用户还能访问吗？

正常情况下会被 Cloudflare 防火墙 + Nginx GeoIP2 双重拦截。如果用户通过代理/VPN 访问，只能依赖应用层的访问日志监控。

---

## 费用预估

| 项目 | 月费 | 年费 |
|------|------|------|
| 域名 (.com) | - | ~$10-14 |
| VPS (Vultr 1GB) | $5 | $60 |
| Cloudflare (免费版) | $0 | $0 |
| Let's Encrypt SSL | $0 | $0 |
| **总计** | **$5** | **~$74** |
