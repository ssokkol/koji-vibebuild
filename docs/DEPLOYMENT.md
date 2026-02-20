# Deployment Guide

Guide for deploying Koji and VibeBuild.

## Table of Contents

- [Requirements](#requirements)
- [Quick Start](#quick-start)
- [Detailed Installation](#detailed-installation)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)

---

## Requirements

### Server (VPS)

- **OS:** Fedora 40+ (recommended)
- **RAM:** minimum 4GB, recommended 8GB+
- **Disk:** 50GB+ (for SRPM/RPM storage)
- **CPU:** 2+ cores
- **Network:** public IP or network-accessible hostname

### Client

- Python 3.9+
- `koji` CLI
- `rpm-build`, `rpm2cpio`
- Network access to Koji server
- **Optional (for ML name resolution):** `scikit-learn >= 1.3`, `joblib >= 1.3`

---

## Quick Start

### 1. Server Preparation

```bash
# On server (Fedora)
sudo dnf update -y
sudo dnf install -y ansible-core python3-pip
```

### 2. Ansible Setup

```bash
# On local machine
git clone https://github.com/vibebuild/vibebuild.git
cd vibebuild/ansible

# Install Ansible collections
ansible-galaxy install -r requirements.yml
```

### 3. Configuration

```bash
# Configure inventory (create or edit inventory/hosts.ini)
vim inventory/hosts.ini

# Specify server IP
# [koji_hub]
# koji-server ansible_host=YOUR_VPS_IP ansible_user=root
```

```bash
# Configure variables
vim group_vars/all.yml

# Change:
# - koji_hub_fqdn: your domain
# - postgresql_password: secure password
# - koji_admin_user: admin username
```

### 4. Run Playbook

```bash
ansible-playbook -i inventory/hosts.ini playbook.yml
```

### 5. Verify

```bash
# Open in browser
https://YOUR_VPS_IP/koji
```

---

## Detailed Installation

### Manual Koji Installation

If you prefer manual installation:

#### 1. Install Packages

```bash
sudo dnf install -y \
    koji-hub \
    koji-hub-plugins \
    koji-builder \
    koji-web \
    postgresql-server \
    httpd \
    mod_ssl \
    mod_wsgi
```

#### 2. PostgreSQL

```bash
# Initialize
sudo postgresql-setup --initdb

# Configure pg_hba.conf
sudo vim /var/lib/pgsql/data/pg_hba.conf
# Add:
# host    koji     koji     127.0.0.1/32    md5

# Start
sudo systemctl enable --now postgresql

# Create database
sudo -u postgres psql
CREATE USER koji WITH PASSWORD 'your_password';
CREATE DATABASE koji OWNER koji;
\q

# Import schema
sudo -u postgres psql koji < /usr/share/doc/koji*/docs/schema.sql
```

#### 3. SSL Certificates

```bash
# Create directories
sudo mkdir -p /etc/pki/koji/{certs,private}

# Generate CA
openssl req -new -x509 -days 3650 -nodes \
    -subj "/CN=Koji CA" \
    -keyout /etc/pki/koji/private/koji_ca.key \
    -out /etc/pki/koji/koji_ca_cert.crt

# Generate server certificate
openssl genrsa -out /etc/pki/koji/certs/server.key 2048
openssl req -new \
    -subj "/CN=koji.example.com" \
    -key /etc/pki/koji/certs/server.key \
    -out /etc/pki/koji/certs/server.csr
openssl x509 -req -days 3650 \
    -in /etc/pki/koji/certs/server.csr \
    -CA /etc/pki/koji/koji_ca_cert.crt \
    -CAkey /etc/pki/koji/private/koji_ca.key \
    -CAcreateserial \
    -out /etc/pki/koji/certs/server.crt

# Generate client certificate (for admin)
openssl genrsa -out /etc/pki/koji/certs/admin.key 2048
openssl req -new \
    -subj "/CN=kojiadmin" \
    -key /etc/pki/koji/certs/admin.key \
    -out /etc/pki/koji/certs/admin.csr
openssl x509 -req -days 3650 \
    -in /etc/pki/koji/certs/admin.csr \
    -CA /etc/pki/koji/koji_ca_cert.crt \
    -CAkey /etc/pki/koji/private/koji_ca.key \
    -out /etc/pki/koji/certs/admin.crt

# Create PEM bundle
cat /etc/pki/koji/certs/admin.crt /etc/pki/koji/certs/admin.key > ~/.koji/client.pem
cp /etc/pki/koji/koji_ca_cert.crt ~/.koji/serverca.crt
```

#### 4. Koji Hub Configuration

```bash
sudo vim /etc/koji-hub/hub.conf
```

```ini
[hub]
DBName = koji
DBUser = koji
DBPass = your_password
DBHost = 127.0.0.1
KojiDir = /mnt/koji
LoginCreatesUser = On
KojiWebURL = https://koji.example.com/koji
```

#### 5. Apache Configuration

See templates in `ansible/roles/koji-hub/templates/`.

#### 6. Initialization

```bash
# Add admin
koji add-user kojiadmin
koji grant-permission admin kojiadmin

# Create tags
koji add-tag fedora-dest
koji add-tag fedora-build --parent fedora-dest --arches x86_64

# Create target
koji add-target fedora-target fedora-build fedora-dest

# Add external repositories
koji add-external-repo -t fedora-build fedora-base \
    "https://mirrors.fedoraproject.org/mirrorlist?repo=fedora-\$releasever&arch=\$basearch"
```

---

## Configuration

### Client Configuration

```bash
# ~/.koji/config
[koji]
server = https://koji.example.com/kojihub
weburl = https://koji.example.com/koji
topurl = https://koji.example.com/kojifiles
cert = ~/.koji/client.pem
serverca = ~/.koji/serverca.crt
```

### VibeBuild Configuration

VibeBuild can be used with command-line options or environment variables:

```bash
# Via CLI
vibebuild \
    --server https://koji.example.com/kojihub \
    --cert ~/.koji/client.pem \
    --serverca ~/.koji/serverca.crt \
    fedora-target my-package.src.rpm

# Via environment variables
export KOJI_SERVER=https://koji.example.com/kojihub
export KOJI_CERT=~/.koji/client.pem
export KOJI_SERVERCA=~/.koji/serverca.crt
vibebuild fedora-target my-package.src.rpm
```

---

## ML Setup (Optional)

VibeBuild includes an ML-based package name resolver that improves handling of complex virtual RPM dependencies. The ML component is fully optional -- VibeBuild works with rule-based resolution alone.

### 1. Install ML Dependencies

```bash
pip install vibebuild[ml]
# or manually:
pip install scikit-learn>=1.3 joblib>=1.3
```

### 2. Collect Training Data

The training script downloads and parses Fedora repository metadata to extract provides-to-package mappings:

```bash
# Collect data from Fedora 40 (default)
python scripts/collect_training_data.py --output data/training_data.json

# Specify release and architecture
python scripts/collect_training_data.py \
    --output data/training_data.json \
    --release 40 \
    --arch x86_64
```

This downloads `primary.xml.gz` from Fedora mirrors and extracts virtual provides (python3dist, pkgconfig, perl, etc.) mapped to real package names. Produces ~50,000-100,000 mappings.

### 3. Train the Model

```bash
python scripts/train_model.py \
    --input data/training_data.json \
    --output vibebuild/data/model.joblib \
    --test-split 0.1
```

The script:
- Trains a TF-IDF + KNN model on the collected data
- Evaluates on a 10% test split (RPM accuracy, SRPM accuracy)
- Saves the model to `vibebuild/data/model.joblib` (~5-15 MB)

### 4. Using in Production

The model is automatically loaded when VibeBuild starts (if the model file exists and scikit-learn is installed).

```bash
# Normal operation (rules + ML fallback)
vibebuild fedora-target my-package.src.rpm

# Disable ML, use only rule-based resolution
vibebuild --no-ml fedora-target my-package.src.rpm

# Disable all name resolution
vibebuild --no-name-resolution fedora-target my-package.src.rpm

# Use a custom model file
vibebuild --ml-model /path/to/model.joblib fedora-target my-package.src.rpm
```

### ML Caching

ML predictions are cached to `~/.cache/vibebuild/ml_name_cache.json`. Clear the cache if the model is retrained:

```bash
rm -f ~/.cache/vibebuild/ml_name_cache.json
```

---

## Troubleshooting

### Connection Issues

**Symptom:** `Connection refused` or `SSL certificate verify failed`

**Solution:**
```bash
# Check that Apache is running
sudo systemctl status httpd

# Check firewall
sudo firewall-cmd --list-ports
sudo firewall-cmd --add-port=443/tcp --permanent
sudo firewall-cmd --reload

# Check certificates
openssl s_client -connect koji.example.com:443
```

### Database Errors

**Symptom:** `Database connection failed`

**Solution:**
```bash
# Check PostgreSQL
sudo systemctl status postgresql

# Check connection
psql -h 127.0.0.1 -U koji -d koji

# Check pg_hba.conf
sudo cat /var/lib/pgsql/data/pg_hba.conf
```

### Build Errors

**Symptom:** `Build failed: createrepo error`

**Solution:**
```bash
# Regenerate repository
koji regen-repo fedora-build

# Check permissions on /mnt/koji
sudo chown -R apache:apache /mnt/koji
```

### Builder Not Connecting

**Symptom:** Builder shows `offline`

**Solution:**
```bash
# Check kojid
sudo systemctl status kojid
sudo journalctl -u kojid -f

# Check builder certificate
ls -la /etc/pki/koji/kojibuilder.pem
```

### Logs

```bash
# Koji Hub
sudo tail -f /var/log/httpd/error_log

# Koji Builder
sudo journalctl -u kojid -f

# PostgreSQL
sudo tail -f /var/lib/pgsql/data/log/postgresql-*.log
```

---

## Monitoring

### Status Check

```bash
# Host status
koji list-hosts

# Active tasks
koji list-tasks

# Repository status
koji list-tags
```

### Metrics

It's recommended to set up monitoring for:
- Disk space on `/mnt/koji`
- Koji task queue
- Builder status
- Hub response time

---

## Upgrading

### Upgrading Koji

```bash
sudo dnf update koji-hub koji-builder koji-web
sudo systemctl restart httpd kojid
```

### Upgrading VibeBuild

```bash
pip install --upgrade vibebuild

# With ML support
pip install --upgrade vibebuild[ml]
```
