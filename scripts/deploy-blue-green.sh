#!/usr/bin/env bash
# ==============================================================================
# Zero-Downtime Blue/Green Deployment Script for Python Flask & Nginx
# ==============================================================================
set -euo pipefail

DOCKER_IMAGE="${1:-${DOCKER_IMAGE:-test-project-python:latest}}"
NGINX_UPSTREAM_CONF="${NGINX_UPSTREAM_CONF:-/etc/nginx/conf.d/flask_upstream.conf}"
BLUE_PORT=5000
GREEN_PORT=5002
MAX_HEALTH_ATTEMPTS=12
HEALTH_RETRY_INTERVAL=3

echo "========================================================================"
echo " Starting Zero-Downtime Blue/Green Deployment"
echo " Image: $DOCKER_IMAGE"
echo " Time:  $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo "========================================================================"

# 1. Determine Docker command prefix
if docker info >/dev/null 2>&1; then
    DOCKER_CMD="docker"
elif sudo -n docker info >/dev/null 2>&1; then
    DOCKER_CMD="sudo docker"
else
    echo "[-] Error: Cannot connect to Docker daemon. Check permissions." >&2
    exit 1
fi

# 2. Determine Docker Compose command
if $DOCKER_CMD compose version >/dev/null 2>&1; then
    DOCKER_COMPOSE="$DOCKER_CMD compose"
elif which docker-compose >/dev/null 2>&1; then
    if docker-compose version >/dev/null 2>&1; then
        DOCKER_COMPOSE="docker-compose"
    else
        DOCKER_COMPOSE="sudo docker-compose"
    fi
else
    echo "[-] Error: Docker Compose is not installed on this system." >&2
    exit 1
fi

# 3. Ensure external network and shared Redis are operational
echo "[+] Ensuring shared external network 'my_external_network' exists..."
$DOCKER_CMD network create my_external_network 2>/dev/null || true

echo "[+] Pulling new application image: $DOCKER_IMAGE..."
$DOCKER_CMD pull "$DOCKER_IMAGE"

echo "[+] Ensuring Redis service is running..."
DOCKER_IMAGE="$DOCKER_IMAGE" $DOCKER_COMPOSE up -d redis

# 4. Determine currently active environment
# We inspect if web-green is currently active in the Nginx upstream or running healthy
IS_GREEN_ACTIVE=false
if [ -f "$NGINX_UPSTREAM_CONF" ] && grep -q "$GREEN_PORT" "$NGINX_UPSTREAM_CONF" 2>/dev/null; then
    IS_GREEN_ACTIVE=true
elif $DOCKER_CMD ps --format '{{.Names}}' | grep -q "^web-green$"; then
    if ! $DOCKER_CMD ps --format '{{.Names}}' | grep -q "^web-blue$"; then
        IS_GREEN_ACTIVE=true
    fi
fi

if [ "$IS_GREEN_ACTIVE" = true ]; then
    ACTIVE_COLOR="green"
    ACTIVE_SERVICE="web-green"
    ACTIVE_PORT=$GREEN_PORT
    TARGET_COLOR="blue"
    TARGET_SERVICE="web-blue"
    TARGET_PORT=$BLUE_PORT
else
    ACTIVE_COLOR="blue"
    ACTIVE_SERVICE="web-blue"
    ACTIVE_PORT=$BLUE_PORT
    TARGET_COLOR="green"
    TARGET_SERVICE="web-green"
    TARGET_PORT=$GREEN_PORT
fi

echo "[+] Active environment: $ACTIVE_COLOR (Port: $ACTIVE_PORT)"
echo "[+] Deploying new version to target environment: $TARGET_COLOR (Port: $TARGET_PORT)"

# 5. Start target container with updated image
echo "[+] Starting $TARGET_SERVICE container..."
DOCKER_IMAGE="$DOCKER_IMAGE" $DOCKER_COMPOSE up -d --no-deps "$TARGET_SERVICE"

# 6. Perform automated readiness health checks on the new container
echo "[+] Verifying health of $TARGET_SERVICE at http://127.0.0.1:$TARGET_PORT/healthz..."
HEALTH_SUCCESS=false

for i in $(seq 1 $MAX_HEALTH_ATTEMPTS); do
    echo "    Attempt $i of $MAX_HEALTH_ATTEMPTS..."
    STATUS_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:$TARGET_PORT/healthz" || true)
    if [ "$STATUS_CODE" = "200" ]; then
        HEALTH_SUCCESS=true
        echo "[+] Health check PASSED on $TARGET_SERVICE (HTTP $STATUS_CODE)!"
        break
    else
        echo "    Health check responded with HTTP $STATUS_CODE. Retrying in ${HEALTH_RETRY_INTERVAL}s..."
        sleep $HEALTH_RETRY_INTERVAL
    fi
done

if [ "$HEALTH_SUCCESS" != true ]; then
    echo "[-] ERROR: Health check FAILED for $TARGET_SERVICE on port $TARGET_PORT after $MAX_HEALTH_ATTEMPTS attempts." >&2
    echo "[-] ABORTING DEPLOYMENT: Live traffic remains safe on $ACTIVE_SERVICE ($ACTIVE_PORT)." >&2
    echo "[-] Tearing down failed $TARGET_SERVICE container..."
    $DOCKER_COMPOSE stop "$TARGET_SERVICE" || true
    $DOCKER_COMPOSE rm -f "$TARGET_SERVICE" || true
    exit 1
fi

# 7. Atomically switch Nginx upstream to target container
echo "[+] Updating Nginx upstream configuration to point to port $TARGET_PORT..."
TMP_CONF=$(mktemp)
cat <<EOF > "$TMP_CONF"
# Upstream configuration for Flask application (Managed by Blue/Green deploy)
upstream flask_web_backend {
    server 127.0.0.1:$TARGET_PORT;
    keepalive 32;
}
EOF

# Move configuration into place with sudo if needed
if [ -w "$(dirname "$NGINX_UPSTREAM_CONF")" ]; then
    mv "$TMP_CONF" "$NGINX_UPSTREAM_CONF"
else
    sudo mv "$TMP_CONF" "$NGINX_UPSTREAM_CONF"
fi

# Test Nginx syntax and reload
echo "[+] Validating Nginx syntax..."
if sudo -n nginx -t >/dev/null 2>&1; then
    sudo nginx -t
    echo "[+] Gracefully reloading Nginx (Zero-Downtime Cutover)..."
    sudo systemctl reload nginx
elif nginx -t >/dev/null 2>&1; then
    nginx -t
    systemctl reload nginx
else
    echo "[-] Warning: Could not execute 'nginx -t'. Attempting reload via systemctl..."
    sudo systemctl reload nginx 2>/dev/null || systemctl reload nginx
fi

echo "[+] Traffic is now serving live from $TARGET_SERVICE (Port $TARGET_PORT)!"

# 8. Gracefully stop previous active container
echo "[+] Gracefully stopping old container: $ACTIVE_SERVICE..."
$DOCKER_COMPOSE stop "$ACTIVE_SERVICE" || true

# 9. Clean up dangling images
echo "[+] Cleaning up dangling Docker images..."
$DOCKER_CMD image prune -f || true

echo "========================================================================"
echo " Zero-Downtime Blue/Green Deployment Finished Successfully!"
echo " Active Service: $TARGET_SERVICE (Port: $TARGET_PORT)"
echo " Image:          $DOCKER_IMAGE"
echo "========================================================================"
