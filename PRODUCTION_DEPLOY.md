# Production Deployment Guide

## 🚀 Deploy to EC2 (Production with Webhook)

### Prerequisites
- ✅ Domain: `telegram.mercle.ai` configured in Route 53
- ✅ EC2 instance: `54.173.40.200`
- ✅ SSH access configured

---

## 📦 Step 1: Copy Files to EC2

```bash
cd /home/ichiro
scp -r telegrambot telegrambot:~/
```

---

## 🔧 Step 2: Deploy on EC2

```bash
# SSH to EC2
ssh telegrambot

# Go to project directory
cd telegrambot

# Setup Python environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run deployment script
sudo ./deploy_production.sh
```

This script will:
1. ✅ Install Nginx
2. ✅ Configure reverse proxy
3. ✅ Get SSL certificate from Let's Encrypt
4. ✅ Create systemd service
5. ✅ Start the bot

**Deployment takes ~5 minutes**

---

## 🔒 Step 3: Configure Security Group

In AWS Console → EC2 → Security Groups:

**Allow these ports:**
- Port 22 (SSH) - Already allowed
- Port 80 (HTTP) - Add this
- Port 443 (HTTPS) - Add this

**Inbound Rules:**
```
Type        Protocol    Port Range    Source
SSH         TCP         22            Your IP
HTTP        TCP         80            0.0.0.0/0
HTTPS       TCP         443           0.0.0.0/0
```

---

## ✅ Step 4: Verify Deployment

### Test DNS Resolution
```bash
nslookup telegram.mercle.ai
# Should return: 54.173.40.200
```

### Test Health Endpoint
```bash
curl https://telegram.mercle.ai/health
# Should return: {"status":"healthy","bot":"online","database":"connected"}
```

### Check Service Status
```bash
sudo systemctl status telegrambot
```

### View Logs
```bash
sudo journalctl -u telegrambot -f
```

---

## 🤖 Step 5: Test the Bot

1. **Open Telegram**
2. **Search:** `@mercleMerci_bot`
3. **Type:** `/start`
4. **Type:** `/verify`
5. **Should receive:** QR code + buttons instantly

---

## 📊 Monitoring Commands

### Check Everything
```bash
./check_status.sh
```

### View Real-time Logs
```bash
sudo journalctl -u telegrambot -f
```

### Restart Bot
```bash
sudo systemctl restart telegrambot
```

### Check Webhook Status
```bash
curl https://telegram.mercle.ai/webhook/info
```

---

## 🔧 Configuration Files

### Environment Variables (.env)
```env
BOT_TOKEN=8015740704:AAEvhfS5UwXOk_dbICe_fC8hmNbm_0RNF-I
MERCLE_API_URL=https://newapi.mercle.ai/api/mercle-sdk
MERCLE_API_KEY=815bb028-825a-414b-96da-fb751ec3c97a
VERIFICATION_TIMEOUT=30
WEBHOOK_URL=https://telegram.mercle.ai
WEBHOOK_PATH=/webhook/secure-random-path
```

### Nginx Config
Location: `/etc/nginx/sites-available/telegrambot`

### Systemd Service
Location: `/etc/systemd/system/telegrambot.service`

---

## 🐛 Troubleshooting

### Bot not responding
```bash
# Check if service is running
sudo systemctl status telegrambot

# Check logs
sudo journalctl -u telegrambot -n 50

# Restart service
sudo systemctl restart telegrambot
```

### SSL certificate issues
```bash
# Renew certificate
sudo certbot renew

# Check certificate status
sudo certbot certificates
```

### Nginx issues
```bash
# Test configuration
sudo nginx -t

# Restart Nginx
sudo systemctl restart nginx

# Check Nginx logs
sudo tail -f /var/log/nginx/error.log
```

### Webhook not working
```bash
# Check webhook info
curl https://telegram.mercle.ai/webhook/info

# Re-register webhook manually
curl -X POST "https://api.telegram.org/bot8015740704:AAEvhfS5UwXOk_dbICe_fC8hmNbm_0RNF-I/setWebhook" \
     -d "url=https://telegram.mercle.ai/webhook/your-secret-path"
```

---

## 🔄 Update Bot Code

When you make changes:

```bash
# Local machine
cd /home/ichiro/telegrambot
git add -A
git commit -m "Update bot"
git push origin main

# EC2
ssh telegrambot
cd telegrambot
git pull origin main
sudo systemctl restart telegrambot
```

---

## 📈 Production Checklist

- [x] DNS configured (telegram.mercle.ai)
- [x] SSL certificate (Let's Encrypt)
- [x] Nginx reverse proxy
- [x] Systemd service
- [x] Webhook configured
- [x] Security group (ports 80, 443)
- [ ] Set up monitoring (CloudWatch)
- [ ] Set up log rotation
- [ ] Configure backups (database)
- [ ] Set up alerts (downtime)

---

## 🎯 Performance

**Current Setup:**
- **Workers**: 2 uvicorn workers
- **Database**: SQLite (good for <1000 users)
- **Server**: EC2 t3.micro

**If you need to scale:**
- Increase workers: `--workers 4`
- Switch to PostgreSQL for more users
- Use Redis for caching
- Add load balancer for multiple instances

---

## 📞 Support

- Bot: @mercleMerci_bot
- Domain: https://telegram.mercle.ai
- Health: https://telegram.mercle.ai/health
- Webhook Info: https://telegram.mercle.ai/webhook/info

