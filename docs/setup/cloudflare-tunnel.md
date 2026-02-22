# Cloudflare Tunnel Setup (Demo / Development Only)

> **Scope:** This setup is for **demo and development testing only**. It routes traffic from Cloudflare's edge through an outbound tunnel to a local Docker stack. Production deployments will require a different solution (e.g. a hosted VM with proper TLS, a container platform with ingress, or a different tunnel/proxy architecture).

This guide sets up Cloudflare Tunnel to provide proper TLS certificates and public access to your local Passing Circle instance.

## Why Cloudflare Tunnel?

WebAuthn (passkeys) requires HTTPS with a valid certificate from a trusted CA. Self-signed certs on `.local` domains fail browser security checks. Cloudflare Tunnel is a quick way to get valid TLS for development without provisioning infrastructure.

- **Proper TLS certificates** — Cloudflare-managed, no self-signed cert issues
- **WebAuthn compatibility** — real domains work with passkeys
- **No port forwarding** — secure outbound-only tunnel
- **Free tier** — no cost for development use

## Prerequisites

- [x] Domain registered: `passingcircle.com`
- [x] Domain added to Cloudflare
- [x] Cloudflare Account ID and API Token (already saved in `.env.cloudflare`)

---

## Step 1: Add Domain to Cloudflare (If Not Already Done)

1. Go to [Cloudflare Dashboard](https://dash.cloudflare.com/)
2. Click **"Add site"**
3. Enter `passingcircle.com`
4. Select Free plan
5. Update your domain's nameservers at your registrar to Cloudflare's nameservers
6. Wait for DNS propagation (usually 5-30 minutes)

---

## Step 2: Create Cloudflare Tunnel

### Option A: Via Cloudflare Dashboard (Recommended)

1. Go to [Cloudflare Zero Trust Dashboard](https://one.dash.cloudflare.com/)
2. Navigate to **Networks** → **Tunnels**
3. Click **"Create a tunnel"**
4. Choose **"Cloudflared"** tunnel type
5. **Tunnel name**: `passingcircle-dev`
6. Click **"Save tunnel"**
7. **IMPORTANT**: Copy the tunnel token shown (format: `eyJh...`)
8. Save the token to `.env.cloudflare`:
   ```bash
   echo "CLOUDFLARE_TUNNEL_TOKEN=your-token-here" >> .env.cloudflare
   ```

### Option B: Via API

```bash
# Source credentials
source .env.cloudflare

# Create tunnel
TUNNEL_NAME="passingcircle-dev"
TUNNEL_SECRET=$(openssl rand -base64 32)

curl -X POST "https://api.cloudflare.com/client/v4/accounts/${CLOUDFLARE_ACCOUNT_ID}/cfd_tunnel" \
  -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
  -H "Content-Type: application/json" \
  --data "{\"name\":\"${TUNNEL_NAME}\",\"tunnel_secret\":\"${TUNNEL_SECRET}\"}"

# Save tunnel ID and token from response
```

---

## Step 3: Configure Tunnel Routes

In the Cloudflare Dashboard (Zero Trust → Tunnels → your tunnel → **Public Hostnames** tab):

### Route 1: Chat Domain
- **Subdomain**: `chat`
- **Domain**: `passingcircle.com`
- **Service Type**: `HTTP`
- **URL**: `passingcircle-nginx:443` (use HTTPS)
- **Additional settings**:
  - **TLS Verification**: Off (self-signed cert between tunnel and NGINX)
  - **HTTP2 Origin**: On
  - **No TLS Verify**: On

### Route 2: Auth Domain
- **Subdomain**: `auth.chat`
- **Domain**: `passingcircle.com`
- **Service Type**: `HTTP`
- **URL**: `passingcircle-nginx:443` (use HTTPS)
- **Additional settings**:
  - **TLS Verification**: Off (self-signed cert between tunnel and NGINX)
  - **HTTP2 Origin**: On
  - **No TLS Verify**: On

**Note**: The tunnel routes to your internal NGINX container which handles the SSL termination with self-signed certs. Cloudflare → Tunnel uses Cloudflare certs, Tunnel → NGINX uses your self-signed certs.

---

## Step 4: Configure DNS Records

Cloudflare should auto-create CNAME records when you configure tunnel routes. Verify in **DNS** tab:

```
chat.passingcircle.com          CNAME   <tunnel-id>.cfargotunnel.com   Proxied
auth.chat.passingcircle.com     CNAME   <tunnel-id>.cfargotunnel.com   Proxied
```

If not created automatically, add them manually with the tunnel ID from Step 2.

---

## Step 5: Update Passing Circle Configuration

Edit `config/passingcircle.yml`:

```yaml
domain: passingcircle.com  # Change from chat.local
server_name: chat.passingcircle.com
matrix:
  server_name: passingcircle.com  # Matrix server name (federation ID)
  auth_domain: auth.chat.passingcircle.com  # Change from auth.chat.local
```

**Regenerate configs**:
```bash
./scripts/setup.sh
```

---

## Step 6: Start Development Environment

```bash
# Ensure tunnel token is set in .env.cloudflare
source .env.cloudflare
echo $CLOUDFLARE_TUNNEL_TOKEN  # Should output your token

# Start services with development overrides
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# Check tunnel status
docker compose logs cloudflare-tunnel

# Should see:
#   "Connection <uuid> registered"
#   "Registered tunnel connection"
```

---

## Step 7: Test Access

1. **Navigate to** `https://chat-mobile.passingcircle.com` (FluffyChat)
2. **Should be** redirected to Authentik for authentication
3. **Click "Register"** → Enrollment flow
4. **Complete enrollment** (username → passkey registration)
5. **Result**: Logged into FluffyChat

Alternatively, visit `https://chat.passingcircle.com` for the landing page with client options.

**Verify TLS**:
- Browser should show valid Cloudflare certificate
- No security warnings
- WebAuthn should work without issues

---

## Step 8: Verify WebAuthn Works

1. Go through enrollment flow
2. When prompted for passkey:
   - Should work without "SecurityError: The operation is insecure"
   - Browser will show standard WebAuthn prompt
   - Platform authenticator (Windows Hello, Touch ID, etc.) should work
3. Complete registration
4. Should be redirected back to FluffyChat and logged in

---

## Troubleshooting

### Tunnel Not Connecting

```bash
# Check tunnel logs
docker compose logs cloudflare-tunnel --tail 100

# Common issues:
# - Invalid token: Regenerate tunnel and get new token
# - Network issues: Check firewall allows outbound HTTPS
# - Container can't reach NGINX: Check Docker network
```

### DNS Not Resolving

```bash
# Check DNS propagation
dig chat.passingcircle.com
nslookup auth.chat.passingcircle.com

# Should return Cloudflare CNAME records
```

### WebAuthn Still Failing

1. **Clear browser cache** completely
2. **Verify domain** in browser address bar shows `chat.passingcircle.com`
3. **Check certificate** - should show Cloudflare Inc.
4. **Try different browser** - Edge/Chrome often have better WebAuthn support

### Tunnel Routes Not Working

1. Go to Cloudflare Dashboard → Zero Trust → Tunnels
2. Click your tunnel → **Public Hostnames** tab
3. **Edit routes** and ensure:
   - Service Type = HTTP
   - URL = `passingcircle-nginx:443`
   - **TLS Verify = OFF** (critical!)
4. **Test** via Cloudflare's tunnel test feature

---

## Limitations

This tunnel setup is **not suitable for production**. Key constraints:

- Depends on the developer's local machine being online and running Docker
- Single point of failure — no redundancy or failover
- Tunnel token stored in a local `.env.cloudflare` file
- No monitoring, alerting, or automated recovery
- Cloudflare Tunnel free tier has no SLA

Production deployments should use a hosted solution with proper TLS certificate management (e.g. Let's Encrypt), redundancy, and secrets management. The Passing Circle stack itself is portable — only the tunnel/proxy layer needs replacing.

---

## Cleanup

To remove development setup:

```bash
# Stop services
docker compose -f docker-compose.yml -f docker-compose.dev.yml down

# Delete tunnel (optional - via dashboard or API)
# Cloudflare Dashboard → Zero Trust → Tunnels → Delete

# Revert config
git checkout config/passingcircle.yml
./scripts/setup.sh
```

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    Internet Users                           │
└─────────────────────┬───────────────────────────────────────┘
                      │
              HTTPS (Cloudflare TLS)
                      │
┌─────────────────────▼───────────────────────────────────────┐
│              Cloudflare Edge Network                        │
│  ┌────────────────────────────────────────────────────┐    │
│  │  chat.passingcircle.com                           │    │
│  │  auth.chat.passingcircle.com                      │    │
│  │                                                     │    │
│  │  • TLS Termination (Cloudflare cert)              │    │
│  │  • DDoS Protection                                 │    │
│  │  • CDN / Caching                                   │    │
│  │  • WAF / Security Rules                            │    │
│  └───────────────────┬────────────────────────────────┘    │
└────────────────────  │  ──────────────────────────────────  ┘
                       │
          Encrypted Tunnel (outbound-only)
                       │
┌──────────────────────▼──────────────────────────────────────┐
│              Local Development Machine                       │
│                                                              │
│  ┌──────────────────────────────────────────────────┐      │
│  │  cloudflared container                           │      │
│  │  (Cloudflare Tunnel endpoint)                    │      │
│  └──────────────────┬───────────────────────────────┘      │
│                     │                                       │
│              Docker network                                 │
│                     │                                       │
│  ┌──────────────────▼───────────────────────────────┐      │
│  │  NGINX (reverse proxy)                          │      │
│  │  • Self-signed cert (internal only)             │      │
│  │  • Routes to Authentik / Synapse / FluffyChat   │      │
│  └──────────┬───────────────────┬──────────────────┘      │
│             │                   │                          │
│  ┌──────────▼──────┐  ┌────────▼─────────────────┐        │
│  │  Authentik      │  │  Synapse + FluffyChat    │        │
│  │  (auth)         │  │  (Matrix chat)           │        │
│  └─────────────────┘  └──────────────────────────┘        │
└─────────────────────────────────────────────────────────────┘
```

**Key Points**:
- Cloudflare handles TLS for external traffic
- Tunnel is encrypted and outbound-only (no open ports)
- Internal traffic uses self-signed certs (not exposed externally)
- NGINX routes traffic to appropriate services

---

## Security Considerations

✅ **Enabled**:
- TLS 1.3 (Cloudflare)
- DDoS protection
- Encrypted tunnel
- No exposed ports
- Rate limiting (Cloudflare)

⚠️ **Consider Adding**:
- Cloudflare Access for auth.chat.passingcircle.com
- IP allow/deny lists
- Bot protection
- Additional WAF rules

---

## Cost

Cloudflare Tunnel is **FREE** for:
- Unlimited bandwidth
- Unlimited tunnels
- Basic DDoS protection
- DNS management

Additional costs only for:
- Cloudflare Access ($3/user/month) - optional
- Advanced WAF rules - optional
- Enterprise features - optional

For development, everything needed is **FREE**.
