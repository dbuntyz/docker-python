# EC2 CI/CD Deployment Guide (GitHub Actions + SSH PEM Key)

This project includes an automated GitHub Actions CI/CD pipeline defined in [`.github/workflows/ci-cd.yml`](.github/workflows/ci-cd.yml).

The pipeline automatically:
1. **Lints** the codebase using `flake8`.
2. **Runs automated tests** with `pytest`, spinning up an ephemeral Redis test service container and generating test coverage reports.
3. **Deploys via SSH to your AWS EC2 instance** using your PEM private key on any push to `main` (or `master`).

---

## 1. Required GitHub Repository Secrets

In your GitHub repository, navigate to:
**Settings** > **Secrets and variables** > **Actions** > Click **New repository secret**.

Add the following secrets:

| Secret Name | Description | Example Value |
|---|---|---|
| `EC2_HOST` | Public IP address or Public DNS of your EC2 instance | `3.85.120.45` or `ec2-3-85-120-45.compute-1.amazonaws.com` |
| `EC2_USER` | SSH username for the EC2 instance | `ubuntu` (for Ubuntu) or `ec2-user` (for Amazon Linux) |
| `EC2_SSH_KEY` | Entire content of your `.pem` private key file | See instructions below |
| `TARGET_DIR` | (Optional) Full path to the repository on your EC2 instance | `/home/ubuntu/test-project-python` (defaults to `/home/<EC2_USER>/test-project-python`) |
| `EC2_PORT` | (Optional) SSH port | `22` (default) |

### How to format `EC2_SSH_KEY`:
Open your `.pem` file with a text editor (e.g. Notepad, VS Code) and copy the **entire** content including header and footer:

```text
-----BEGIN RSA PRIVATE KEY-----
MIIEowIBAAKCAQEA...
...
...
-----END RSA PRIVATE KEY-----
```
*(Or `-----BEGIN OPENSSH PRIVATE KEY-----` ... `-----END OPENSSH PRIVATE KEY-----`)*

---

## 2. AWS EC2 Instance Prerequisites

Before running the deployment for the first time, ensure the EC2 instance is prepared:

### A. AWS Security Group (Firewall)
Ensure your EC2 Security Group allows inbound SSH traffic:
- **Type**: SSH
- **Protocol**: TCP
- **Port Range**: `22`
- **Source**: `0.0.0.0/0` (or restricted to GitHub's runner IP ranges for higher security)

### B. Install Docker & Docker Compose on EC2
Connect to your EC2 instance via SSH:
```bash
ssh -i /path/to/your-key.pem ubuntu@<EC2_PUBLIC_IP>
```

Run the following commands on the EC2 instance (Ubuntu):
```bash
# 1. Update packages and install Docker
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch="$(dpkg --print-architecture)" signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  "$(. /etc/os-release && echo "$VERSION_CODENAME")" stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 2. Allow non-root user to run Docker commands
sudo usermod -aG docker $USER
newgrp docker
```

### C. Clone the Repository on EC2 (First-time setup)
In your user home directory on EC2:
```bash
# Clone the repository
git clone https://github.com/<YOUR_USERNAME>/<YOUR_REPOSITORY>.git /home/ubuntu/test-project-python

# Navigate into the project
cd /home/ubuntu/test-project-python

# Create the external network required by docker-compose.yml
docker network create my_external_network || true
```

---

## 3. How the Pipeline Works

```mermaid
flowchart LR
    A[Push / PR to main] --> B[Job 1: Linting]
    A --> C[Job 2: Pytest & Coverage]
    B --> D{Lint & Tests Pass?}
    C --> D
    D -- Yes (Push to main) --> E[Job 3: Deploy to EC2 via SSH]
    D -- No / PR --> F[Stop Pipeline]
    E --> G[Pull latest code on EC2]
    G --> H[Rebuild & Restart Docker Containers]
    H --> I[Deployment Complete]
```

1. **Lint Job**:
   Runs `flake8 .` enforcing code style and catching syntax errors before any tests or deployment.
2. **Test Job**:
   Launches a background `redis:alpine` service on port 6371 and runs `pytest tests/` with full test coverage metrics.
3. **Deploy Job**:
   Uses `appleboy/ssh-action` to connect securely to your EC2 instance with the PEM private key, pulls the latest code from GitHub, ensures the external Docker network is present, and restarts the containers using `docker compose up -d --build`.

---

## 4. Local Testing & Verification

You can run the same linting and tests locally anytime:

```bash
# Install dependencies
pip install -r requirements.txt -r requirements-dev.txt

# Run linter
flake8 .

# Run test suite with coverage
pytest tests/ -v --cov=. --cov-report=term-missing
```
