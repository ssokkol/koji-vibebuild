# Deployment Guide

Руководство по развертыванию Koji и VibeBuild.

## Содержание

- [Требования](#требования)
- [Быстрый старт](#быстрый-старт)
- [Подробная установка](#подробная-установка)
- [Конфигурация](#конфигурация)
- [Troubleshooting](#troubleshooting)

---

## Требования

### Сервер (VPS)

- **ОС:** Fedora 40+ (рекомендуется)
- **RAM:** минимум 4GB, рекомендуется 8GB+
- **Диск:** 50GB+ (для хранения SRPM/RPM)
- **CPU:** 2+ cores
- **Сеть:** публичный IP или доступный из сети hostname

### Клиент

- Python 3.9+
- `koji` CLI
- `rpm-build`, `rpm2cpio`
- Сетевой доступ к Koji серверу

---

## Быстрый старт

### 1. Подготовка сервера

```bash
# На сервере (Fedora)
sudo dnf update -y
sudo dnf install -y ansible-core python3-pip
```

### 2. Настройка Ansible

```bash
# На локальной машине
git clone https://github.com/vibebuild/vibebuild.git
cd vibebuild/ansible

# Установить Ansible коллекции
ansible-galaxy install -r requirements.yml
```

### 3. Конфигурация

```bash
# Настроить inventory
cp inventory/hosts.ini.example inventory/hosts.ini
vim inventory/hosts.ini

# Указать IP сервера
# [koji_hub]
# koji-server ansible_host=YOUR_VPS_IP ansible_user=root
```

```bash
# Настроить переменные
vim group_vars/all.yml

# Изменить:
# - koji_hub_fqdn: ваш домен
# - postgresql_password: безопасный пароль
# - koji_admin_user: имя администратора
```

### 4. Запуск playbook

```bash
ansible-playbook -i inventory/hosts.ini playbook.yml
```

### 5. Проверка

```bash
# Открыть в браузере
https://YOUR_VPS_IP/koji
```

---

## Подробная установка

### Установка Koji вручную

Если вы предпочитаете ручную установку:

#### 1. Установка пакетов

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
# Инициализация
sudo postgresql-setup --initdb

# Настройка pg_hba.conf
sudo vim /var/lib/pgsql/data/pg_hba.conf
# Добавить:
# host    koji     koji     127.0.0.1/32    md5

# Запуск
sudo systemctl enable --now postgresql

# Создание БД
sudo -u postgres psql
CREATE USER koji WITH PASSWORD 'your_password';
CREATE DATABASE koji OWNER koji;
\q

# Импорт схемы
sudo -u postgres psql koji < /usr/share/doc/koji*/docs/schema.sql
```

#### 3. SSL сертификаты

```bash
# Создать директории
sudo mkdir -p /etc/pki/koji/{certs,private}

# Генерация CA
openssl req -new -x509 -days 3650 -nodes \
    -subj "/CN=Koji CA" \
    -keyout /etc/pki/koji/private/koji_ca.key \
    -out /etc/pki/koji/koji_ca_cert.crt

# Генерация сертификата сервера
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

# Генерация клиентского сертификата (для admin)
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

# Создать PEM bundle
cat /etc/pki/koji/certs/admin.crt /etc/pki/koji/certs/admin.key > ~/.koji/client.pem
cp /etc/pki/koji/koji_ca_cert.crt ~/.koji/serverca.crt
```

#### 4. Конфигурация Koji Hub

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

#### 5. Настройка Apache

См. шаблоны в `ansible/roles/koji-hub/templates/`.

#### 6. Инициализация

```bash
# Добавить админа
koji add-user kojiadmin
koji grant-permission admin kojiadmin

# Создать теги
koji add-tag fedora-dest
koji add-tag fedora-build --parent fedora-dest --arches x86_64

# Создать таргет
koji add-target fedora-target fedora-build fedora-dest

# Добавить внешние репозитории
koji add-external-repo -t fedora-build fedora-base \
    "https://mirrors.fedoraproject.org/mirrorlist?repo=fedora-\$releasever&arch=\$basearch"
```

---

## Конфигурация

### Клиентская конфигурация

```bash
# ~/.koji/config
[koji]
server = https://koji.example.com/kojihub
weburl = https://koji.example.com/koji
topurl = https://koji.example.com/kojifiles
cert = ~/.koji/client.pem
serverca = ~/.koji/serverca.crt
```

### VibeBuild конфигурация

VibeBuild можно использовать с опциями командной строки или переменными окружения:

```bash
# Через CLI
vibebuild \
    --server https://koji.example.com/kojihub \
    --cert ~/.koji/client.pem \
    --serverca ~/.koji/serverca.crt \
    fedora-target my-package.src.rpm

# Через переменные окружения
export KOJI_SERVER=https://koji.example.com/kojihub
export KOJI_CERT=~/.koji/client.pem
export KOJI_SERVERCA=~/.koji/serverca.crt
vibebuild fedora-target my-package.src.rpm
```

---

## Troubleshooting

### Проблемы с подключением

**Симптом:** `Connection refused` или `SSL certificate verify failed`

**Решение:**
```bash
# Проверить, что Apache запущен
sudo systemctl status httpd

# Проверить firewall
sudo firewall-cmd --list-ports
sudo firewall-cmd --add-port=443/tcp --permanent
sudo firewall-cmd --reload

# Проверить сертификаты
openssl s_client -connect koji.example.com:443
```

### Ошибки базы данных

**Симптом:** `Database connection failed`

**Решение:**
```bash
# Проверить PostgreSQL
sudo systemctl status postgresql

# Проверить подключение
psql -h 127.0.0.1 -U koji -d koji

# Проверить pg_hba.conf
sudo cat /var/lib/pgsql/data/pg_hba.conf
```

### Ошибки сборки

**Симптом:** `Build failed: createrepo error`

**Решение:**
```bash
# Регенерировать репозиторий
koji regen-repo fedora-build

# Проверить права на /mnt/koji
sudo chown -R apache:apache /mnt/koji
```

### Builder не подключается

**Симптом:** Builder показывает `offline`

**Решение:**
```bash
# Проверить kojid
sudo systemctl status kojid
sudo journalctl -u kojid -f

# Проверить сертификат builder'а
ls -la /etc/pki/koji/kojibuilder.pem
```

### Логи

```bash
# Koji Hub
sudo tail -f /var/log/httpd/error_log

# Koji Builder
sudo journalctl -u kojid -f

# PostgreSQL
sudo tail -f /var/lib/pgsql/data/log/postgresql-*.log
```

---

## Мониторинг

### Проверка состояния

```bash
# Статус хостов
koji list-hosts

# Активные задачи
koji list-tasks

# Статус репозитория
koji list-tags
```

### Метрики

Рекомендуется настроить мониторинг для:
- Дисковое пространство `/mnt/koji`
- Очередь задач Koji
- Статус builder'ов
- Время отклика Hub

---

## Обновление

### Обновление Koji

```bash
sudo dnf update koji-hub koji-builder koji-web
sudo systemctl restart httpd kojid
```

### Обновление VibeBuild

```bash
pip install --upgrade vibebuild
```
