# Production CI/CD & Deployment Guide (DevSecOps + Blue/Green)

This repository features a hardened, production-grade GitHub Actions CI/CD pipeline defined in [`.github/workflows/ci-cd.yml`](.github/workflows/ci-cd.yml).

The pipeline incorporates:
1. **Secret Scanning (Gitleaks)**: Scans commits and history to prevent sensitive keys/tokens from being leaked.
2. **Static Analysis & Linting (Flake8)**: Enforces Python code quality.
3. **Automated Unit & Integration Tests (Pytest)**: Runs tests against an ephemeral Redis service with coverage reporting.
4. **Vulnerability Scanning (Trivy Filesystem & Container Image)**: Scans repository dependencies, Dockerfile, and container image for CVEs before deployment.
5. **Container Registry (Docker Hub)**: Builds multi-layer images with Buildx caching and pushes immutable SHA-tagged releases.
6. **Zero-Downtime Blue/Green Deployment**: Automates zero-downtime container swapping on AWS EC2 with health verification and instant Nginx upstream reload.

---

## 1. Required GitHub Repository Secrets

In your GitHub repository, navigate to:
**Settings** > **Secrets and variables** > **Actions** > Click **New repository secret**.

Add the following secrets:

| Secret Name | Description | Example Value |
|---|---|---|
| `DOCKERHUB_USERNAME` | Docker Hub username or organization | `myusername` |
| `DOCKERHUB_TOKEN` | Docker Hub Personal Access Token (Read/Write) | `dckr_pat_xxxxxxxxxxxx` |
| `DOCKERHUB_REPOSITORY` | *(Optional)* Docker Hub repository name (defaults to `test-project-python`) | `test-project-python` |
| `EC2_HOST` | Public IP address or Public DNS of your EC2 instance | `35.154.69.69` |
| `EC2_USER` | SSH username for the EC2 instance | `ubuntu` |
| `EC2_SSH_KEY` | Entire content of your `.pem` private key file | See instructions below |
| `TARGET_DIR` | *(Optional)* Full path to project on EC2 | `/home/ubuntu/test-project-python` |
| `EC2_PORT` | *(Optional)* SSH port | `22` (default) |

### How to format `EC2_SSH_KEY`:
Open your `.pem` file with a text editor and copy the **entire** content including header and footer:

```text
-----BEGIN RSA PRIVATE KEY-----
MIIEowIBAAKCAQEA...
...
-----END RSA PRIVATE KEY-----
```

---

## 2. Pipeline Architecture & Workflow

```mermaid
flowchart TD
    subgraph CI["CI & Security Gates"]
        A[Push / PR] --> B[Job 1: Gitleaks Secret Scan]
        A --> C[Job 2: Flake8 Code Style]
        A --> D[Job 3: Pytest & Redis Coverage]
        A --> E[Job 4: Trivy FS Vulnerability Scan]
    end

    subgraph CD_REGISTRY["Container Build & Registry"]
        B & C & D & E --> F{All CI Gates Pass?}
        F -- Yes (main branch) --> G[Job 5: Docker Buildx Build]
        G --> H[Trivy Container Image Scan]
        H --> I[Push to Docker Hub :sha and :latest]
    end

    subgraph CD_DEPLOY["Zero-Downtime Blue/Green Deployment (EC2)"]
        I --> J[Job 6: SSH to EC2]
        J --> K[Pull latest image from Docker Hub]
        K --> L[Detect active color: Blue:5000 or Green:5002]
        L --> M[Start idle container with new image]
        M --> N{Health Check /healthz?}
        N -- Failed --> O[Tear down idle container\nActive remains safe & live]
        N -- Passed --> P[Switch Nginx upstream & reload nginx]
        P --> Q[Stop previous active container]
        Q --> R[Deployment Complete - Zero Downtime]
    end
```

---

## 3. How Blue/Green Deployment Works on EC2

The deployment script [`scripts/deploy-blue-green.sh`](scripts/deploy-blue-green.sh) coordinates zero-downtime updates:

| Environment | Service Name in Compose | Host Port | Status |
|---|---|---|---|
| **Blue** | `web-blue` | `5000` | Alternates between Active and Idle |
| **Green** | `web-green` | `5002` | Alternates between Active and Idle |
| **Redis** | `redis-service` | `6371` | Shared across both environments |

### Zero-Downtime Cutover Process:
1. **Detect Active Environment**: The script reads `/etc/nginx/conf.d/flask_upstream.conf` or inspects running containers.
2. **Deploy to Idle Environment**: The new version from Docker Hub is launched on the idle port (`5000` or `5002`).
3. **Automated Health Check**: The script queries `http://127.0.0.1:<target_port>/healthz` up to 12 times (every 3 seconds).
   - If the health check **fails**, the idle container is automatically stopped and removed. The live container is never touched, and the pipeline fails safely.
4. **Nginx Upstream Reload**: If the health check **passes**, the script updates `/etc/nginx/conf.d/flask_upstream.conf`, validates the syntax (`nginx -t`), and gracefully reloads Nginx (`systemctl reload nginx`).
5. **Old Container Teardown**: The old container is gracefully stopped, and dangling Docker images are pruned.

---

## 4. Nginx Server Configuration

On your EC2 host, the Nginx configuration at `/etc/nginx/sites-enabled/task.techokay.in` includes the dynamic upstream file:

```nginx
# Include the dynamic Blue/Green upstream definition
include /etc/nginx/conf.d/flask_upstream.conf;
```

Where `/etc/nginx/conf.d/flask_upstream.conf` is dynamically maintained:
```nginx
upstream flask_web_backend {
    server 127.0.0.1:5000; # or 127.0.0.1:5002
    keepalive 32;
}
```

Reference templates are available in:
- [`nginx/task.techokay.in.conf`](nginx/task.techokay.in.conf)
- [`nginx/conf.d/flask_upstream.conf`](nginx/conf.d/flask_upstream.conf)

---

## 5. Local Testing & Verification

You can run local linting and tests anytime before committing:

```bash
# Activate virtual environment
source .venv/bin/activate  # Or .\.venv\Scripts\Activate.ps1 on Windows

# Run linter
flake8 .

# Run test suite with coverage
pytest tests/ -v --cov=. --cov-report=term-missing
```
