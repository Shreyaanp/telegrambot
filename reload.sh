#!/bin/bash
# Quick reload script for development

echo "🔄 Reloading bot..."
sudo systemctl restart telegrambot

echo "⏳ Waiting for bot to start..."
sleep 3

echo "📊 Checking status..."
sudo systemctl status telegrambot --no-pager -l | head -15

echo ""
echo "✅ Bot reloaded!"
echo ""
echo "📋 View logs: sudo journalctl -u telegrambot -f"
echo "🏥 Check health: curl http://localhost:8000/health"

