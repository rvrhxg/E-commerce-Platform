from fastapi.testclient import TestClient
from app.main import create_app
from app.models import Product
import os
import uuid
from urllib.parse import quote
import pytest
from sqlalchemy import create_engine, text


@pytest.fixture(params=['sqlite', 'postgres'])
def app(request, tmp_path):
    if request.param == 'sqlite':
        yield create_app(f"sqlite:///{tmp_path / 'catalog.sqlite'}")
        return
    url = os.environ.get('TEST_POSTGRES_URL')
    if not url:
        pytest.skip('PostgreSQL URL not configured')
    schema = 'catalog_' + uuid.uuid4().hex
    root = create_engine(url)
    with root.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    try:
        yield create_app(url + '?options=' + quote(f'-csearch_path={schema}'))
    finally:
        with root.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        root.dispose()


def test_catalog_filters_unicode_literal_search_and_insert_stable_cursor(app):
    with app.state.sessions.begin() as session:
        session.add_all([Product(sku=f'p{i}', title='Чаша 100%' if i < 4 else 'Other', category='ceramics',
                                price_kopecks=100*i, stock=i) for i in range(6)])
    with TestClient(app) as client:
        query = '/api/catalog?q=ЧАША&category=ceramics&min_price=100&max_price=400&in_stock=true&limit=2'
        first = client.get(query).json()
        assert len(first['items']) == 2
        with app.state.sessions.begin() as session:
            session.add(Product(sku='later',title='Чаша later',category='ceramics',price_kopecks=200,stock=2))
        second = client.get(query+'&cursor='+first['next_cursor']).json()
        assert len(second['items']) == 1
        assert second['next_cursor'] is None
        assert {p['id'] for p in first['items']}.isdisjoint(p['id'] for p in second['items'])
        assert len(client.get('/api/catalog?q=%25').json()['items']) == 4
        assert client.get('/api/catalog?q=changed&cursor='+first['next_cursor']).status_code == 400
        assert client.get('/api/catalog?cursor=not-valid').status_code == 400
        assert client.get('/api/catalog?min_price=4&max_price=2').status_code == 422
