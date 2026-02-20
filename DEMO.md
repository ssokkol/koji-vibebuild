# Демонстрация VibeBuild

Пошаговая последовательность для публичной демонстрации возможностей vibebuild. Можно выполнить **всё в один запуск**: указать имя пакета вместо пути к SRPM — vibebuild скачает SRPM и соберёт пакет.

---

## 1. Предусловия

- **ОС:** Fedora 43 или Fedora 42.
- **Пакеты:** установите при необходимости:
  ```bash
  sudo dnf install koji rpm-build rpm2cpio
  ```
- **Python:** 3.9 или выше. Рекомендуется виртуальное окружение:
  ```bash
  python3 -m venv .venv && source .venv/bin/activate
  ```

---

## 2. Установка vibebuild

Клонируйте репозиторий и установите пакет с поддержкой ML (для резолва имён вроде `python3` и виртуальных provides):

```bash
git clone https://github.com/vibebuild/vibebuild.git
cd vibebuild
pip install -e ".[ml]"
```

Проверка:

```bash
vibebuild --version
vibebuild --help
```

При необходимости полный список опций:

```bash
vibebuild --help-all
```

---

## 3. Демо 0: одна команда — скачать и собрать

Вместо пути к файлу можно передать **имя пакета**: vibebuild сам скачает SRPM из Koji и запустит сборку (с разрешением зависимостей):

```bash
vibebuild fedora-43 python3
```

Аналогично для любого пакета:

```bash
vibebuild fedora-43 python-requests
vibebuild --scratch fedora-43 python-aiohttp
```

Сначала в логе появится загрузка SRPM, затем построение графа зависимостей и сборка.

---

## 4. Демо 1: только загрузка SRPM

Резолв короткого имени `python3` в версионированный пакет (например `python3.14` на F43) и загрузка SRPM из Fedora Koji:

```bash
vibebuild --download-only python3
```

Ожидаемый вывод (или аналог):

```
Resolved 'python3' -> python3.14
Downloaded: python3.14-3.14.x-x.fc43.src.rpm
```

Загрузка пакета с виртуальными зависимостями:

```bash
vibebuild --download-only python-requests
```

Файлы сохраняются в текущий каталог (или в каталог, заданный через `--download-dir`). В выводе будет указан путь, например:

```
Downloaded: python-requests-x.x.x-x.fc43.src.rpm
```

---

## 5. Демо 2: анализ зависимостей

Подставьте путь к скачанному SRPM (например `python-requests-*.src.rpm`):

```bash
vibebuild --analyze-only ./python-requests-2.31.0-1.fc43.src.rpm
```

В выводе будут:

- имя пакета и NVR;
- список **BuildRequires**;
- при настроенном Koji — отсутствующие зависимости (какие пакеты нужно доставить/собрать).

---

## 6. Демо 3: граф сборки (dry-run)

Показать порядок уровней сборки без реальной сборки:

```bash
vibebuild --dry-run fedora-43 ./python-requests-2.31.0-1.fc43.src.rpm
```

(Для Fedora 42 используйте target `fedora-42`; для других веток — соответствующий target.)

В выводе:

- уровни сборки (level 0, 1, 2, …);
- список пакетов по уровням.

При реальной сборке для отсутствующих зависимостей будут выводиться сообщения вида «Downloading dependency: …» и «Downloaded: …».

---

## 7. Демо 4 (опционально): реальная сборка

При наличии доступа к Koji можно выполнить scratch-сборку:

```bash
vibebuild --scratch fedora-43 ./python-requests-2.31.0-1.fc43.src.rpm
```

**Scratch** — сборка без тегирования; результат можно смотреть в веб-интерфейсе Koji по задаче сборки.

---

## 8. Шпаргалка команд

| Режим                | Пример команды                                      | Что делает |
|----------------------|------------------------------------------------------|------------|
| Скачать и собрать    | `vibebuild fedora-43 python3`                        | Скачивание SRPM по имени, затем полная сборка с зависимостями |
| Скачать и собрать    | `vibebuild fedora-43 python-requests`                | То же по имени пакета |
| Только загрузка      | `vibebuild --download-only python3`                  | Резолв имени, скачивание SRPM из Koji |
| Только анализ        | `vibebuild --analyze-only <путь к .src.rpm>`         | Парсинг spec, вывод BuildRequires и отсутствующих |
| Dry-run              | `vibebuild --dry-run fedora-43 <путь или имя>`       | Граф сборки по уровням, без сборки |
| Сборка по пути       | `vibebuild fedora-43 <путь к .src.rpm>`              | Полная сборка с разрешением зависимостей |
| Scratch-сборка      | `vibebuild --scratch fedora-43 python-requests`      | Scratch-сборка в Koji (имя или путь) |

---

## 9. Примечания

- **Koji:** настройки по умолчанию берутся из `~/.koji/config`. Свой сервер можно задать через `--server`. Все опции: `vibebuild --help-all`.
- **Резолв имён:** для коротких имён (например `python3`) используется модель, обученная с алиасами из `vibebuild/data/alias_training.json`. При переходе на новую версию Fedora можно обновить этот файл и переобучить модель (`scripts/collect_training_data.py`, `scripts/train_model.py`).
