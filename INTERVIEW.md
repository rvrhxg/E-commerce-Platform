# Atelier Commerce — разбор для собеседования

Сверено 20 ноября 2026 с текущими файлами app/main.py, models.py, checkout.py, database.py, security.py, миграциями, Dockerfile и compose.yaml. Ключевые main/models/checkout сверены с GitHub. Это объяснение существующего учебного MVP, не заявление о коммерческой эксплуатации. Примеры ниже извлечены из исходников; номера строк относятся к состоянию на дату проверки.

## Архитектура и выполнение запроса

Один процесс FastAPI обслуживает REST API и статические HTML/CSS/JavaScript. Браузер обращается к тому же origin; отдельного frontend-сервера, очереди и микросервисов нет. `app/main.py` собирает приложение фабрикой create_app, валидирует вход через Pydantic и вызывает прикладные функции. SQLAlchemy Session создаётся на запрос/операцию. Engine управляет соединениями; `pool_pre_ping=True` проверяет их перед использованием. Локально по умолчанию SQLite, в compose — PostgreSQL 17 через psycopg.

`app/models.py` описывает SQLAlchemy2 declarative-модели: Base — общий metadata, Mapped[T] — тип атрибута, mapped_column — конфигурация колонки. Типы не заменяют ограничения БД. Связи реализованы ForeignKey и явными SELECT/JOIN: relationship/back_populates и автоматическая загрузка коллекций не объявлены. Наличие FK на пользователя и категорию само по себе не проверяет совпадение владельцев: это делает приложение.

## Авторизация и безопасность

Это серверные opaque-сессии, не JWT. Пароль проверяется scrypt с индивидуальной солью; сравнение через hmac.compare_digest. Токен — secrets.token_hex(32), в БД хранится SHA256 токена, не его исходное значение. Cookie HttpOnly, SameSite=Strict, Secure включается при ENVIRONMENT=production; срок сессии 24 часа проверяется сервером. Logout удаляет строку сессии. identity извлекает пользователя из cookie; фильтр user_id применяется отдельно в запросах к данным.

Middleware ограничивает размер тела и для изменяющих запросов требует JSON и точный Origin. Устанавливаются security headers, для статических страниц — CSP. Это защита браузерных запросов, не замена авторизации. Регистрация нормализует email и не позволяет запросом назначить расширенные права. Ограничитель входа хранится в памяти процесса и не распределён между workers. Нет MFA, восстановления пароля, подтверждения email и централизованного управления сессиями. Синхронный scrypt вызывается из auth handler: подтверждённых нагрузочных гарантий нет.

## Alembic и жизненный цикл БД

Схема обновляется миграциями, а не Base.metadata.create_all в обычном запуске. `app/database.py` передаёт существующее соединение Alembic через config.attributes. По умолчанию create_app вызывает database с initialize=True, поэтому демо-процесс выполняет upgrade head при старте. Для развёртывания нескольких workers миграции лучше выполнять отдельным шагом до запуска. `expire_on_commit=False` оставляет загруженные атрибуты доступными после commit, но не делает их автоматически свежими. SQLite-соединения получают PRAGMA foreign_keys=ON; в Commerce дополнительно регистрируется Unicode lower.

`session.begin()` коммитит при нормальном выходе и откатывает при исключении. `flush()` отправляет SQL и выдаёт ID/ошибки ограничений, но не завершает транзакцию. Если ошибка перехвачена снаружи context manager, изменения уже откатились. `with sessions()` без begin закрывает Session; записывающие операции должны иметь явную транзакцию.

## Docker и эксплуатация

Dockerfile использует python:3.14-slim и requirements.lock; приложение запускается не от root, UID 1000. Копируются app, public и миграции, стартует uvicorn с --no-access-log. Healthcheck обращается к /api/ready; /api/health — liveness. Readiness проверяет соединение и наличие версии схемы, но не весь бизнес-процесс и не точное совпадение head.

Compose поднимает PostgreSQL 17, сохраняет данные в именованном томе и ждёт pg_isready. Пароль задаётся через POSTGRES_PASSWORD, не встроен в образ. Порт приложения привязан к 127.0.0.1; TLS proxy в compose нет. down -v удаляет данные тома. Нужны отдельные настройки HTTPS/APP_ORIGIN и секретов. Конфигурация демонстрационная: высокая доступность, нагрузочное тестирование и аварийные RPO/RTO не подтверждены. Backup/restore и их ограничения описаны в docs/OPERATIONS.md; резервные копии не публикуются.

## Модели и связи

| Модель | Назначение и ограничения |
|---|---|
| User | Уникальный email, имя, hash пароля, is_admin=False по умолчанию |
| LoginSession | PK token_hash, FK user_id, expires_at — Unix seconds |
| Product | Уникальный sku, цена/остаток с CHECK >=0, active; category — строка, не отдельная таблица |
| Order | FK user_id, UNIQUE(user_id,idempotency_key), request_hash, сумма BigInteger, адрес, статус, время создания |
| OrderItem | FK order_id/product_id, снимок названия и цены, количество |
| Cart | UNIQUE FK user_id: у пользователя максимум одна корзина; revision для проверки версии |
| CartItem | FK cart_id с ON DELETE CASCADE, FK product_id, UNIQUE(cart_id,product_id), CHECK количества 1..99 |

User связан с несколькими сессиями/заказами, максимум одной корзиной. Order содержит много OrderItem; Product участвует во многих позициях заказов и корзин. Это связи1:N через FK; таблицы позиций разрешают связь заказов и товаров. Каскадное удаление явно задано только там, где оно есть в FK; ORM-cascade не настроен. Итог заказа BigInteger, цены товара/позиции — целые числа в копейках; плавающая арифметика для расчёта итога не нужна.

Миграции: 0001 исходная схема; 0002 индекс orders(user_id,id); 0003 корзины/позиции; 0004 revision. Откат 0003 удаляет сохранённые корзины, не заказы. Для старой базы без Alembic следует сначала прочитать docs/MIGRATIONS.md: слепой stamp не подтверждает совпадение схемы.

## Заказ и корзина

POST /api/orders открывает sessions.begin, определяет пользователя, вызывает checkout и формирует ответ до выхода из транзакции. checkout валидирует позиции, сортирует их по ID, отвергает дубликаты, вычисляет hash нормализованных позиций и адреса. Повтор ключа с тем же hash возвращает прежний заказ; другой hash даёт конфликт. UNIQUE(user_id,key) остаётся последним барьером при гонке, HTTP409 предлагает повторить запрос.

PostgreSQL FOR UPDATE блокирует строки товара; условный UPDATE stock>=quantity не даёт списать больше остатка. Порядок ID уменьшает риск взаимных блокировок, но не гарантирует отсутствие всех deadlock. SQLite FOR UPDATE не реализует блокировку строк; нельзя переносить на неё объяснение PostgreSQL. Заказ, позиции, списание и подходящая очистка корзины коммитятся вместе. Отмена возвращает остаток в транзакции смены статуса; допустимые переходы проверяет доменный код.

PUT корзины требует revision, DELETE — query revision. UPDATE с условием на revision увеличивает версию; если rowcount!=1, возвращается409. Новая корзина начинается с0. Checkout может принять cart_revision: при совпадении удаляет только совпавшие отправленные позиции; при изменении корзины сохраняет её. Повтор заказа выходит до очистки. Без cart_revision остаётся прежний контракт заказа без очистки. Корзина не резервирует товар и не фиксирует цену.

## Три участка кода: построчный разбор

### [app/main.py:100](app/main.py#L100)

```python
    def identity(request, session):
        token = request.cookies.get("session", "")
        login = session.get(LoginSession, token_hash(token)) if len(token) == 64 else None
        if not login or login.expires_at <= int(time.time()):
            raise HTTPException(401, "Authentication required")
        return session.get(User, login.user_id)
```

| Строка | Объяснение |
|---|---|
| 100 | Получает Request и текущую SQLAlchemy Session. |
| 101 | Читает cookie, отсутствие заменяет пустой строкой. |
| 102 | При длине64 ищет PK сессии по SHA256, не по raw-токену. Это не полная проверка формата токена. |
| 103 | Отвергает отсутствующую или истёкшую сессию. |
| 104 | Возвращает HTTP401 до доступа к данным. |
| 105 | Загружает User; авторизация конкретного ресурса выполняется отдельно. |

### [app/checkout.py:38](app/checkout.py#L38)

```python
    for product_id, quantity in normalized:
        product = session.scalar(select(Product).where(Product.id == product_id, Product.active.is_(True)).with_for_update())
        if not product:
            raise CheckoutConflict("Product unavailable")
        changed = session.execute(update(Product).where(Product.id == product_id, Product.stock >= quantity).values(stock=Product.stock-quantity))
        if changed.rowcount != 1:
            raise CheckoutConflict("Not enough stock")
        lines.append(OrderLine(product.id, product.title, product.price_kopecks, quantity))
```

| Строка | Объяснение |
|---|---|
| 38 | Обрабатывает позиции в заранее отсортированном порядке. |
| 39 | Выбирает только активный товар; PostgreSQL блокирует строку FOR UPDATE. |
| 40 | Проверяет, найден ли товар. |
| 41 | Конфликт прерывает внешнюю транзакцию. |
| 42 | Условно уменьшает остаток только если stock>=quantity; значения передаются параметрами SQL. |
| 43 | Проверяет число реально изменённых строк. |
| 44 | При нехватке остатка исключение откатывает и предыдущие списания. |
| 45 | Сохраняет серверную цену/название в доменную позицию для снимка заказа. |

### [app/main.py:219](app/main.py#L219)

```python
                changed = session.execute(update(Cart).where(Cart.id == cart.id, Cart.revision == data.revision).values(revision=Cart.revision + 1))
                if changed.rowcount != 1:
                    raise HTTPException(409, "Cart changed; reload before editing")
```

| Строка | Объяснение |
|---|---|
| 219 | Compare-and-swap: меняет версию только выбранной корзины с ожидаемой revision; увеличение выполняется SQL-выражением. |
| 220 | Ноль обновлённых строк означает устаревшую версию. |
| 221 | HTTP409 выходит из begin с откатом; клиент перечитывает корзину. |

## Ограничения и что реально проверено

Это не платёжный сервис: оплаты, доставки, уведомлений, восстановления пароля и подтверждённой production-эксплуатации нет. Cursor каталога фиксирует верхний ID, но не замораживает изменения товаров. Заказы используют offset. Конфликты редактирования корзины не сливаются автоматически. Проверка остатков выполняется при записи и повторно при заказе. Нет нагрузочного теста, независимого security-аудита и подтверждённых аварийных RPO/RTO.

Тесты: tests/test_checkout.py (снимки/повторы/откат), test_cart.py (владельцы/вход/версии), test_cart_atomic.py (очистка/повтор/устаревший снимок/откат, SQLite и opt-in PostgreSQL), test_migrations.py (сохранность/upgrade/downgrade/check), test_postgres.py (гонка за остаток). Дополнительные HTTP/security/catalog/backup/readiness тесты находятся в tests. PostgreSQL-тесты пропускаются без TEST_POSTGRES_URL.

Предыдущий подтверждённый [CI 44513906168](https://github.com/rvrhxg/E-commerce-Platform/actions/runs/44513906168) на 3317056: Python3.12–3.14 с PostgreSQL, Docker/runtime, Chromium и запись демо. Это доказательство того коммита, не произвольной будущей версии. Последующий визуальный проход выполнялся локально headless Chrome; свежий полный CI визуальных правок здесь не объявляется подтверждённым. Новый локальный pytest-прогон для этого документа фиксируется отдельно ниже. Ruff E9/F охватывает app/tests/scripts; strict mypy — только 4 модуля из pyproject.toml, не весь backend.

Быстрый ответ на собеседовании: «Граница атомарности — внешний Session.begin. Цена берётся с сервера, остаток защищён условным UPDATE, повтор запроса — ключом и hash, а очистка корзины — версией снимка. Эти гарантии проверяются отдельными регрессиями, но не означают готовность к платежам и высокой нагрузке».

## Локальный прогон 20 ноября 2026

Python 3.14, `python -m pytest -q`: **24 passed, 6 skipped**. Пропуски связаны с отсутствующим TEST_POSTGRES_URL. Это не новый локальный PostgreSQL/Docker/Chromium-прогон и не повтор всей матрицы Python. Есть предупреждение Starlette о deprecated интеграции TestClient/httpx; тесты завершились успешно. Для временных файлов использован отдельный basetemp внутри рабочей папки.

В этой задаче изменён только INTERVIEW.md; бизнес-код, миграции и конфигурация не редактировались.
