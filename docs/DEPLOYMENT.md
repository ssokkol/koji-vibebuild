# Руководство по развёртыванию

Руководство по развёртыванию Koji и VibeBuild.

## Содержание

- [Требования](#требования)
- [Быстрый старт](#быстрый-старт)
- [Подробная установка](#подробная-установка)
- [Конфигурация](#конфигурация)
- [Устранение неполадок](#устранение-неполадок)

---

## Требования

### Сервер (VPS)

- **ОС:** Fedora 40+ (рекомендуется)
- **RAM:** минимум 4 ГБ, рекомендуется 8 ГБ+
- **Диск:** 50 ГБ+ (для хранения SRPM/RPM)
- **CPU:** 2+ ядра
- **Сеть:** публичный IP или доступное по сети имя хоста

### Клиент

- Python 3.9+
- `koji` CLI
- `rpm-build`, `rpm2cpio`
- Сетевой доступ к серверу Koji
- **Опционально (для ML-разрешения имён):** `scikit-learn >= 1.3`, `joblib >= 1.3`

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

# Установка коллекций Ansible
ansible-galaxy install -r requirements.yml
```

### 3. Конфигурация

```bash
# Настройка inventory (создайте или отредактируйте inventory/hosts.ini)
vim inventory/hosts.ini

# Укажите IP сервера
# [koji_hub]
# koji-server ansible_host=YOUR_VPS_IP ansible_user=root
```

```bash
# Настройка переменных
vim group_vars/all.yml

# Измените:
# - koji_hub_fqdn: ваш домен
# - postgresql_password: надёжный пароль
# - koji_admin_user: имя администратора
```

### 4. Запуск плейбука

```bash
ansible-playbook -i inventory/hosts.ini playbook.yml
```

### 5. Проверка

```bash
# Откройте в браузере
https://YOUR_VPS_IP/koji
```

---

## Подробная установка

### Ручная установка Koji

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
# Добавьте:
# host    koji     koji     127.0.0.1/32    md5

# Запуск
sudo systemctl enable --now postgresql

# Создание базы данных
sudo -u postgres psql
CREATE USER koji WITH PASSWORD 'your_password';
CREATE DATABASE koji OWNER koji;
\q

# Импорт схемы
sudo -u postgres psql koji < /usr/share/doc/koji*/docs/schema.sql
```

#### 3. SSL-сертификаты

```bash
# Создание каталогов
sudo mkdir -p /etc/pki/koji/{certs,private}

# Генерация CA
openssl req -new -x509 -days 3650 -nodes \
    -subj "/CN=Koji CA" \
    -keyout /etc/pki/koji/private/koji_ca.key \
    -out /etc/pki/koji/koji_ca_cert.crt

# Генерация серверного сертификата
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

# Генерация клиентского сертификата (для администратора)
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

# Создание PEM-бандла
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

#### 5. Конфигурация Apache

Шаблоны см. в `ansible/roles/koji-hub/templates/`.

#### 6. Инициализация

```bash
# Добавление администратора
koji add-user kojiadmin
koji grant-permission admin kojiadmin

# Создание тегов
koji add-tag fedora-dest
koji add-tag fedora-build --parent fedora-dest --arches x86_64

# Создание цели сборки
koji add-target fedora-target fedora-build fedora-dest

# Добавление внешних репозиториев
koji add-external-repo -t fedora-build fedora-base \
    "https://mirrors.fedoraproject.org/mirrorlist?repo=fedora-\$releasever&arch=\$basearch"
```

---

## Конфигурация

### Конфигурация клиента

```bash
# ~/.koji/config
[koji]
server = https://koji.example.com/kojihub
weburl = https://koji.example.com/koji
topurl = https://koji.example.com/kojifiles
cert = ~/.koji/client.pem
serverca = ~/.koji/serverca.crt
```

### Конфигурация VibeBuild

VibeBuild можно настроить через опции командной строки или переменные окружения:

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

## Настройка ML (опционально)

VibeBuild включает ML-резолвер имён пакетов, который улучшает обработку сложных виртуальных RPM-зависимостей. ML-компонент полностью опционален — VibeBuild работает и с одними правилами.

### 1. Установка ML-зависимостей

```bash
pip install vibebuild[ml]
# или вручную:
pip install scikit-learn>=1.3 joblib>=1.3
```

### 2. Сбор обучающих данных

Скрипт скачивает и парсит метаданные репозиториев Fedora для извлечения маппингов provides-to-package:

```bash
# Сбор данных из Fedora 40 (по умолчанию)
python scripts/collect_training_data.py --output data/training_data.json

# Указание релиза и архитектуры
python scripts/collect_training_data.py \
    --output data/training_data.json \
    --release 40 \
    --arch x86_64
```

Скрипт скачивает `primary.xml.gz` с зеркал Fedora и извлекает виртуальные provides (python3dist, pkgconfig, perl и др.), привязанные к реальным именам пакетов. Результат — ~50 000–100 000 маппингов.

### 3. Обучение модели

```bash
python scripts/train_model.py \
    --input data/training_data.json \
    --output vibebuild/data/model.joblib \
    --test-split 0.1
```

Скрипт:
- Обучает модель TF-IDF + KNN на собранных данных
- Оценивает на 10% тестовой выборке (RPM accuracy, SRPM accuracy)
- Сохраняет модель в `vibebuild/data/model.joblib` (~5–15 МБ)

### 4. Использование в продакшене

Модель автоматически загружается при запуске VibeBuild (если файл модели существует и scikit-learn установлен).

```bash
# Обычная работа (правила + ML как запасной вариант)
vibebuild fedora-target my-package.src.rpm

# Отключить ML, использовать только правила
vibebuild --no-ml fedora-target my-package.src.rpm

# Отключить всё разрешение имён
vibebuild --no-name-resolution fedora-target my-package.src.rpm

# Использовать пользовательский файл модели
vibebuild --ml-model /path/to/model.joblib fedora-target my-package.src.rpm
```

### Кэширование ML

ML-предсказания кэшируются в `~/.cache/vibebuild/ml_name_cache.json`. Очистите кэш при переобучении модели:

```bash
rm -f ~/.cache/vibebuild/ml_name_cache.json
```

---

## Устранение неполадок

### Проблемы с подключением

**Симптом:** `Connection refused` или `SSL certificate verify failed`

**Решение:**
```bash
# Проверьте, запущен ли Apache
sudo systemctl status httpd

# Проверьте файрвол
sudo firewall-cmd --list-ports
sudo firewall-cmd --add-port=443/tcp --permanent
sudo firewall-cmd --reload

# Проверьте сертификаты
openssl s_client -connect koji.example.com:443
```

### Ошибки базы данных

**Симптом:** `Database connection failed`

**Решение:**
```bash
# Проверьте PostgreSQL
sudo systemctl status postgresql

# Проверьте подключение
psql -h 127.0.0.1 -U koji -d koji

# Проверьте pg_hba.conf
sudo cat /var/lib/pgsql/data/pg_hba.conf
```

### Ошибки сборки

**Симптом:** `Build failed: createrepo error`

**Решение:**
```bash
# Регенерация репозитория
koji regen-repo fedora-build

# Проверьте права на /mnt/koji
sudo chown -R apache:apache /mnt/koji
```

### Builder не подключается

**Симптом:** Builder в статусе `offline`

**Решение:**
```bash
# Проверьте kojid
sudo systemctl status kojid
sudo journalctl -u kojid -f

# Проверьте сертификат builder
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

### Проверка статуса

```bash
# Статус хостов
koji list-hosts

# Активные задачи
koji list-tasks

# Статус репозитория
koji list-tags
```

### Метрики

Рекомендуется настроить мониторинг:
- Дисковое пространство на `/mnt/koji`
- Очередь задач Koji
- Статус builder
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

# С поддержкой ML
pip install --upgrade vibebuild[ml]
```
