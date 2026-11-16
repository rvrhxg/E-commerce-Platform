# Приёмка портфолио

Проверено в CI 43858094326: Python-тесты домена, SQLAlchemy rollback/идемпотентность, API/роли, отмена заказа, конкурентная покупка последней единицы на PostgreSQL. Docker build и запуск с PostgreSQL прошли: заказ сохранился после перезапуска, вход повторён, процесс работает от UID1000. Chromium выполнил регистрацию, корзину, оформление и историю заказа. Desktop/mobile/корзина/заказ просмотрены визуально, снимки опубликованы.

Итоговый CI 43858930840 для коммита 84b4e671 успешно повторил проверки после изменения CSP и сообщений об ошибках. Приёмка портфолио v1 завершена.

Ограничения явно указаны в README: без реальной оплаты, уведомлений и доставки внешними службами; корзина в памяти вкладки; списки до 200; нет миграций и восстановления пароля. PostgreSQL-тест подтверждает конкретный сценарий одновременной покупки, но не заменяет нагрузочное тестирование. Сервис не заявлен production-готовым или коммерческим опытом.

Обновление Alembic/пагинации/авторизации и Python 3.12–3.14: [UPDATE-ACCEPTANCE.md](UPDATE-ACCEPTANCE.md).


## Readiness, безопасные HTTP-логи и backup/restore

[CI 43929968154](https://github.com/rvrhxg/E-commerce-Platform/actions/runs/43929968154) на d361533: все job успешны на Python3.12/3.13/3.14. Проверены200/503 readiness, реальная недоступность БД/структуры, request_id и отсутствие URL/query/cookie/тела/секрета в JSON-событиях, общий500 без внутреннего текста, SQLite WAL-snapshot/restore, запрет перезаписи и повреждённый источник. PostgreSQL-матрица выполнила pg_dump/pg_restore между двумя временными базами с BigInteger/внешним ключом, проверила непустую цель и новый файл. Использовался клиент postgres17 в Docker. Docker build/runtime/readiness/persistence и Chromium успешны. Локально: 18 passed, 3 skipped; PostgreSQL локально не установлен. Strict mypy охватывает новые эксплуатационные модули и ранее указанный типизированный модуль, RuffE9/F — app/tests/scripts. Шифрование/ротация/offsite/PITR и аварийные RPO/RTO не проверены; это остаётся MVP. [Инструкции](OPERATIONS.md).


## Recorded demonstration

CI 43939426454 passed. The published WebM is 34.42 seconds at 1280x888, without audio, with explicitly documented 3x playback slowdown. File SHA256 matches metadata; six-frame contact sheet was visually reviewed. This is a Chromium recording with fictional data. It does not establish production readiness or real Telegram delivery.
