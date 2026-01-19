# Contributing to VibeBuild

Спасибо за интерес к VibeBuild! Этот документ описывает процесс внесения изменений в проект.

## Содержание

- [Настройка окружения разработки](#настройка-окружения-разработки)
- [Структура проекта](#структура-проекта)
- [Code Style](#code-style)
- [Работа с Git](#работа-с-git)
- [Pull Request](#pull-request)
- [Тестирование](#тестирование)
- [Документация](#документация)

## Настройка окружения разработки

### Требования

- Python 3.9+
- Git
- `koji` CLI (для интеграционных тестов)
- `rpm-build`, `rpm2cpio` (для работы с SRPM)

### Установка

1. Форкните репозиторий и клонируйте его:

```bash
git clone https://github.com/YOUR_USERNAME/vibebuild.git
cd vibebuild
```

2. Создайте виртуальное окружение:

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# или
.venv\Scripts\activate     # Windows
```

3. Установите зависимости для разработки:

```bash
pip install -e ".[dev]"
```

4. Установите pre-commit hooks:

```bash
pre-commit install
```

### Проверка установки

```bash
# Запуск тестов
pytest

# Проверка code style
black --check vibebuild
isort --check vibebuild
flake8 vibebuild
mypy vibebuild
```

## Структура проекта

```
vibebuild/
├── vibebuild/              # Основной пакет
│   ├── __init__.py         # Экспорты и версия
│   ├── analyzer.py         # Парсинг SRPM/spec файлов
│   ├── resolver.py         # Разрешение зависимостей, DAG
│   ├── fetcher.py          # Загрузка SRPM из Fedora
│   ├── builder.py          # Оркестрация сборок Koji
│   ├── cli.py              # CLI интерфейс
│   └── exceptions.py       # Пользовательские исключения
├── ansible/                # Ansible playbook для Koji
│   ├── playbook.yml
│   ├── inventory/
│   ├── group_vars/
│   └── roles/
├── tests/                  # Тесты
│   ├── test_analyzer.py
│   ├── test_resolver.py
│   └── ...
├── docs/                   # Документация
│   ├── ARCHITECTURE.md
│   ├── API.md
│   └── ...
├── setup.py
├── pyproject.toml
└── requirements*.txt
```

## Code Style

### Python

Мы используем:
- **Black** для форматирования кода (line-length: 100)
- **isort** для сортировки импортов (profile: black)
- **flake8** для линтинга
- **mypy** для проверки типов

Конфигурация в `pyproject.toml`.

```bash
# Автоформатирование
black vibebuild tests
isort vibebuild tests

# Проверка
black --check vibebuild tests
isort --check vibebuild tests
flake8 vibebuild tests
mypy vibebuild
```

### Типизация

Используйте type hints для всех публичных функций:

```python
def get_build_requires(srpm_path: str) -> list[str]:
    """Docstring..."""
    ...
```

### Docstrings

Используйте Google style docstrings:

```python
def build_package(srpm_path: str, wait: bool = True) -> BuildTask:
    """
    Submit a single package build to Koji.
    
    Args:
        srpm_path: Path to SRPM file
        wait: Whether to wait for build to complete
        
    Returns:
        BuildTask with result information
        
    Raises:
        FileNotFoundError: If SRPM doesn't exist
        KojiBuildError: If build fails
    """
```

## Работа с Git

### Структура веток

- `main` — стабильная версия
- `develop` — текущая разработка
- `feature/*` — новые фичи
- `bugfix/*` — исправления багов
- `release/*` — подготовка релизов

### Создание ветки

```bash
# Новая фича
git checkout develop
git pull origin develop
git checkout -b feature/my-feature

# Исправление бага
git checkout -b bugfix/issue-123
```

### Commit Messages

Формат: `<type>(<scope>): <description>`

Типы:
- `feat` — новая функциональность
- `fix` — исправление бага
- `docs` — изменения документации
- `style` — форматирование, без изменения логики
- `refactor` — рефакторинг без изменения функциональности
- `test` — добавление/изменение тестов
- `chore` — обновление зависимостей, конфигов

Примеры:

```
feat(resolver): add circular dependency detection
fix(fetcher): handle network timeout errors
docs(readme): add installation instructions
test(analyzer): add tests for spec parsing
```

## Pull Request

### Checklist

Перед созданием PR убедитесь:

- [ ] Код соответствует code style (black, isort, flake8)
- [ ] Добавлены/обновлены тесты
- [ ] Все тесты проходят (`pytest`)
- [ ] Обновлена документация (если нужно)
- [ ] Commit messages соответствуют формату
- [ ] PR имеет понятное описание

### Процесс

1. Запушьте ветку в свой форк
2. Создайте Pull Request в `develop`
3. Заполните шаблон PR
4. Дождитесь code review
5. Внесите запрошенные изменения
6. После апрува — squash & merge

### Шаблон PR

```markdown
## Описание
Краткое описание изменений

## Тип изменения
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation

## Как тестировал?
Описание тестирования

## Checklist
- [ ] Тесты проходят
- [ ] Code style OK
- [ ] Документация обновлена
```

## Тестирование

### Запуск тестов

```bash
# Все тесты
pytest

# С coverage
pytest --cov=vibebuild --cov-report=html

# Конкретный файл
pytest tests/test_analyzer.py

# Конкретный тест
pytest tests/test_analyzer.py::test_parse_spec
```

### Структура тестов

Используйте AAA pattern (Arrange-Act-Assert):

```python
def test_get_build_requires_returns_list():
    srpm_path = "fixtures/test-package.src.rpm"
    
    result = get_build_requires(srpm_path)
    
    assert isinstance(result, list)
    assert "python3-devel" in result
```

### Fixtures

Тестовые данные в `tests/fixtures/`:

```
tests/
├── fixtures/
│   ├── test-package.spec
│   └── test-package.src.rpm
├── conftest.py
└── test_*.py
```

## Документация

### Обновление документации

При изменении публичного API обновите:

1. Docstrings в коде
2. `docs/API.md`
3. `README.md` (если затрагивает usage)

### Сборка документации

```bash
# Проверка docstrings
pydocstyle vibebuild
```

## Вопросы?

- Создайте Issue с вопросом
- Напишите в discussions

Спасибо за ваш вклад! 🎉
