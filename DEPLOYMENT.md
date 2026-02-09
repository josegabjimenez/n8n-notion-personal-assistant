# VPS Deployment Guide - HTTP Server

Step-by-step guide to deploy the new HTTP server on your VPS.

---

## Prerequisites

- VPS with Python 3.8+ installed
- Git repository cloned at `/root/notion-personal-agent`
- OpenAI API key ready
- Port 8080 available (or choose different port)

---

## Deployment Steps

### Step 1: Connect to VPS and Pull Latest Changes

```bash
# SSH into your VPS
ssh root@your-vps-ip

# Navigate to project directory
cd /root/notion-personal-agent

# Pull latest changes
git pull origin main

# Verify new files exist
ls -la src/http_server.py src/ai_client.py notion-agent-http.service
```

Expected output:
```
-rw-r--r-- 1 root root  5234 Jan 12 23:30 src/http_server.py
-rw-r--r-- 1 root root  4567 Jan 12 23:30 src/ai_client.py
-rw-r--r-- 1 root root   312 Jan 12 23:30 notion-agent-http.service
```

---

### Step 2: Install New Dependencies

```bash
# Activate virtual environment
source .venv/bin/activate

# Install new dependencies
pip install openai fastapi "uvicorn[standard]"

# Verify installations
python -c "import openai, fastapi, uvicorn; print('✓ All packages installed')"
```

---

### Step 3: Update Environment Variables

```bash
# Edit .env file
nano .env
```

Add/update these variables:
```bash
# OpenAI Configuration
OPENAI_API_KEY=sk-your-actual-openai-api-key-here
OPENAI_MODEL=gpt-4.1-nano
OPENAI_TIMEOUT=30

# HTTP Server Configuration
HTTP_HOST=0.0.0.0
HTTP_PORT=8080
DEADLINE_SECONDS=8.0

# Existing Notion variables (keep as-is)
NOTION_API_KEY=...
NOTION_TASKS_DATABASE_ID=...
# ... etc
```

Save and exit (Ctrl+X, then Y, then Enter)

Verify configuration:
```bash
cat .env | grep -E "OPENAI|HTTP"
```

---

### Step 4: Test HTTP Server Manually (Optional but Recommended)

```bash
# Test run the server (Ctrl+C to stop)
source .venv/bin/activate
uvicorn src.http_server:app --host 0.0.0.0 --port 8080

# Keep this terminal open and open a NEW SSH session to test
```

In a **new terminal/SSH session**:
```bash
# Test health endpoint
curl http://localhost:8080/health

# Expected: {"status":"healthy","service":"notion-agent","version":"2.0.0"}

# Test query endpoint
curl -X POST http://localhost:8080/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Hola", "timeout": 8.0}'

# Expected: {"response":"Hola! ¿En qué puedo ayudarte?","status":"completed","task_id":null}
```

If tests pass, press Ctrl+C in the first terminal to stop the server.

---

### Step 5: Install Systemd Service

```bash
# Copy service file to systemd directory
sudo cp notion-agent-http.service /etc/systemd/system/

# Verify it's copied correctly
cat /etc/systemd/system/notion-agent-http.service

# Reload systemd to recognize new service
sudo systemctl daemon-reload

# Enable service to start on boot
sudo systemctl enable notion-agent-http

# Start the service
sudo systemctl start notion-agent-http

# Check status
sudo systemctl status notion-agent-http
```

Expected output:
```
● notion-agent-http.service - Notion Personal Agent HTTP Server
     Loaded: loaded (/etc/systemd/system/notion-agent-http.service; enabled)
     Active: active (running) since ...
```

---

### Step 6: Verify Service is Running

```bash
# Check if service is active
sudo systemctl is-active notion-agent-http

# View recent logs
sudo journalctl -u notion-agent-http -n 50 --no-pager

# Follow logs in real-time (Ctrl+C to stop)
sudo journalctl -u notion-agent-http -f
```

Test the service:
```bash
# Test from VPS
curl http://localhost:8080/health

# Test from external (replace with your VPS IP)
curl http://your-vps-ip:8080/health
```

---

### Step 7: Configure Firewall (If Needed)

If you're using UFW firewall:
```bash
# Allow port 8080
sudo ufw allow 8080/tcp

# Check firewall status
sudo ufw status
```

If using cloud provider firewall (AWS, DigitalOcean, etc.):
- Add inbound rule: TCP port 8080 from your n8n server IP

---

### Step 8: Update n8n Workflow

In your n8n workflow:

**Before (SSH Node):**
```
SSH Command: python /root/notion-personal-agent/src/client.py "{{$json.query}}"
```

**After (HTTP Request Node):**
```
Method: POST
URL: http://your-vps-ip:8080/query
Headers:
  Content-Type: application/json
Body (JSON):
{
  "query": "{{$json.query}}",
  "timeout": 8.0
}
```

---

### Step 9: Test Full Alexa Flow

1. Trigger from Alexa: "Alexa, ask my assistant what tasks I have for today"
2. Check n8n execution logs
3. Verify response comes back within 8 seconds
4. Check VPS logs: `sudo journalctl -u notion-agent-http -f`

---

## Service Management Commands

```bash
# Start service
sudo systemctl start notion-agent-http

# Stop service
sudo systemctl stop notion-agent-http

# Restart service (after code changes)
sudo systemctl restart notion-agent-http

# Check status
sudo systemctl status notion-agent-http

# View logs
sudo journalctl -u notion-agent-http -n 100

# Follow logs in real-time
sudo journalctl -u notion-agent-http -f
```

---

## Troubleshooting

### Service Won't Start

```bash
# Check detailed error
sudo journalctl -u notion-agent-http -n 50

# Common issues:
# 1. Port already in use
sudo lsof -i :8080

# 2. Python path wrong in service file
which python  # Should match service file

# 3. Missing dependencies
source .venv/bin/activate
pip list | grep -E "openai|fastapi|uvicorn"
```

### Slow Responses

```bash
# Check logs for timing info
sudo journalctl -u notion-agent-http -f | grep "AI response received"

# Should see: "AI response received in 1.23s (API call: 1.20s, output: 234 chars)"

# If API calls are slow (>5s), try different model in .env:
OPENAI_MODEL=gpt-4o-mini  # Usually faster than gpt-4.1-nano
```

### OpenAI API Errors

```bash
# Check logs for API errors
sudo journalctl -u notion-agent-http | grep "OpenAI API error"

# Verify API key is correct
cat .env | grep OPENAI_API_KEY

# Test API key manually
source .venv/bin/activate
python -c "
from openai import OpenAI
import os
from dotenv import load_dotenv
load_dotenv()
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
response = client.chat.completions.create(
    model='gpt-4o-mini',
    messages=[{'role': 'user', 'content': 'test'}],
    max_completion_tokens=10
)
print('✓ API key works!')
"
```

---

## Rollback to Old Method (If Needed)

If you need to rollback to the old socket server:

```bash
# Stop HTTP service
sudo systemctl stop notion-agent-http
sudo systemctl disable notion-agent-http

# Start old socket server
python /root/notion-personal-agent/src/server.py

# Or as systemd service (if you had it set up)
sudo systemctl start notion-agent  # Your old service name
```

Then revert n8n workflow back to SSH command.

---

## Performance Monitoring

Check performance in logs:
```bash
# Filter for timing information
sudo journalctl -u notion-agent-http | grep "AI response received"

# Example output:
# AI response received in 1.45s (API call: 1.42s, output: 156 chars)
# AI response received in 2.13s (API call: 2.10s, output: 234 chars)
```

Expected timings:
- Fast classification: <1ms (keyword match)
- Notion API: 500-800ms
- OpenAI API: 1-3s (gpt-4.1-nano or gpt-4o-mini)
- Total: 1.5-4s (well under 8s deadline)

---

## Security Best Practices

1. **Restrict port access** - Only allow n8n server IP
2. **Keep API keys secure** - Never commit .env to git
3. **Regular updates** - Keep dependencies updated
4. **Monitor logs** - Set up log rotation

```bash
# Set up log rotation
sudo nano /etc/logrotate.d/notion-agent

# Add:
/var/log/notion-agent.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
}
```

---

## Next Steps After Deployment

1. ✅ Monitor first few Alexa requests in real-time
2. ✅ Verify response times are under 8 seconds
3. ✅ Check OpenAI usage dashboard for costs
4. ✅ Set up alerts for service failures (optional)
5. ✅ Consider adding HTTPS with nginx reverse proxy (optional)

---

## Support

If you encounter issues:
1. Check logs: `sudo journalctl -u notion-agent-http -f`
2. Verify .env configuration
3. Test OpenAI API key manually
4. Check firewall/port access
5. Review error messages in logs
