# VibeBuild

**Koji extension for automatic dependency resolution and building**

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

VibeBuild расширяет функциональность Koji, добавляя автоматическое разрешение зависимостей. Когда вы собираете пакет, VibeBuild автоматически находит недостающие BuildRequires, скачивает их SRPM из Fedora и собирает всю цепочку зависимостей в правильном порядке.

## Возможности

- 🔍 **Автоматический анализ зависимостей** — парсинг SRPM/spec файлов для извлечения BuildRequires
- 📦 **Загрузка SRPM** — автоматическая загрузка недостающих пакетов из Fedora Koji
- 🔗 **Построение DAG** — определение порядка сборки с учётом зависимостей
- 🏗️ **Оркестрация сборок** — последовательная сборка с ожиданием регенерации репозитория
- 🖥️ **CLI интерфейс** — удобная командная строка

## Быстрый старт

### Установка

```bash
pip install vibebuild
```

Или из исходников:

```bash
git clone https://github.com/vibebuild/vibebuild.git
cd vibebuild
pip install -e .
```

### Использование

```bash
# Сборка пакета с автоматическим разрешением зависимостей
vibebuild fedora-target my-package-1.0-1.fc40.src.rpm

# Scratch сборка (не тегируется)
vibebuild --scratch fedora-target my-package.src.rpm

# Анализ зависимостей без сборки
vibebuild --analyze-only my-package.src.rpm

# Загрузка SRPM из Fedora
vibebuild --download-only python-requests

# Dry run — показать что будет собрано
vibebuild --dry-run fedora-target my-package.src.rpm
```

### Использование с собственным Koji сервером

```bash
vibebuild \
  --server https://koji.example.com/kojihub \
  --web-url https://koji.example.com/koji \
  --cert ~/.koji/client.pem \
  --serverca ~/.koji/serverca.crt \
  --build-tag my-build \
  my-target my-package.src.rpm
```

## Развертывание Koji

В репозитории есть Ansible playbook для автоматического развертывания Koji на Fedora:

```bash
cd ansible

# Настройте inventory
vim inventory/hosts.ini

# Настройте переменные
vim group_vars/all.yml

# Запустите playbook
ansible-playbook -i inventory/hosts.ini playbook.yml
```

## Как это работает

```
┌─────────────────┐
│  vibebuild CLI  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────────┐
│    Analyzer     │────▶│  Parse SRPM     │
│                 │     │  Extract deps   │
└────────┬────────┘     └─────────────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────────┐
│    Resolver     │────▶│  Check Koji     │
│                 │     │  Build DAG      │
└────────┬────────┘     └─────────────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────────┐
│    Fetcher      │────▶│  Download SRPM  │
│                 │     │  from Fedora    │
└────────┬────────┘     └─────────────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────────┐
│    Builder      │────▶│  koji build     │
│                 │     │  wait-repo      │
└─────────────────┘     └─────────────────┘
```

1. **Analyzer** — извлекает BuildRequires из SRPM/spec файла
2. **Resolver** — проверяет какие зависимости отсутствуют в Koji и строит граф зависимостей
3. **Fetcher** — скачивает SRPM для недостающих пакетов из Fedora
4. **Builder** — собирает пакеты в правильном порядке, ожидая регенерацию репозитория между сборками

## Требования

- Python 3.9+
- `koji` CLI (установлен в системе)
- `rpm-build`, `rpm2cpio` (для работы с SRPM)
- Доступ к Koji серверу

## Документация

- [ARCHITECTURE.md](docs/ARCHITECTURE.md) — архитектура системы
- [API.md](docs/API.md) — документация API модулей
- [DEPLOYMENT.md](docs/DEPLOYMENT.md) — руководство по развертыванию
- [CONTRIBUTING.md](CONTRIBUTING.md) — как внести вклад

## Лицензия

MIT License. См. [LICENSE](LICENSE) для деталей.
