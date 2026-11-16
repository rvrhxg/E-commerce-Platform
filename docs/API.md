# REST API

Swagger: /docs, OpenAPI: /openapi.json. Для изменяющих запросов нужны Origin, совпадающий с APP_ORIGIN, и Content-Type application/json. Лимит тела 64 KiB. Авторизация — cookie session, HttpOnly/SameSite=Strict, Secure в production.

| Метод | Путь | Тело / результат |
|---|---|---|
| POST | /api/auth/register | email, password, name; всегда клиент |
| POST | /api/auth/login | email, password |
| POST | /api/auth/logout | Отзыв текущей сессии |
| GET | /api/auth/me | Профиль |
| GET | /api/products | Активные товары, до 200 |
| POST | /api/orders | items: [{product_id,quantity}], address, idempotency_key |
| GET | /api/orders | Только заказы текущего клиента, до 200 |
| POST | /api/admin/products | sku, title, description?, category?, price_kopecks, stock |
| GET | /api/admin/orders | Заказы магазина, только администратор |
| PATCH | /api/admin/orders/:id | status |
| GET | /api/health | Ответ HTTP-процесса |

Статусы: placed → processing → shipped → delivered; placed/processing можно отменить в cancelled. Отмена возвращает остатки один раз. Повторный запрос с одинаковым ключом и содержимым возвращает тот же заказ; с другим содержимым — 409. При конкурентном конфликте повторите исходный запрос с тем же ключом после отката.

Цены присылает сервер, клиент не задаёт итоговую сумму. quantity — целое число от 1 до 99; bool и дроби отвергаются. Сумма товара ограничена 100000000 копеек. Ошибки: 400 доменные данные, 401 сессия, 403 Origin/роль, 409 остатки/ключ/статус/SKU, 413 размер, 415 media type, 422 схема Pydantic, 429 вход. Подробности — поле detail.
