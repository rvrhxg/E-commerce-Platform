from pathlib import Path
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def config(connection):
    cfg = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    cfg.attributes['connection'] = connection
    return cfg


def test_versioned_upgrade_data_survival_downgrade_and_reupgrade(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'migrations.sqlite'}")
    with engine.begin() as connection:
        cfg = config(connection)
        command.upgrade(cfg, '0001')
        connection.execute(text("INSERT INTO users VALUES(1,'migration@example.test','Buyer','hash',0)"))
        connection.execute(text("INSERT INTO orders VALUES(1,1,'migration-key','hash',100,'placed','Address','2026-01-01')"))
        command.upgrade(cfg, 'head')
        assert connection.scalar(text('SELECT version_num FROM alembic_version')) == '0004'
        assert connection.scalar(text('SELECT total_kopecks FROM orders')) == 100
        assert 'ix_orders_user_id_id' in {i['name'] for i in inspect(connection).get_indexes('orders')}
        command.downgrade(cfg, '0001')
        assert connection.scalar(text('SELECT count(*) FROM orders')) == 1
        command.upgrade(cfg, 'head')
        command.upgrade(cfg, 'head')
        command.check(cfg)
    engine.dispose()


def test_revision_upgrade_preserves_saved_cart(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'cart-upgrade.sqlite'}")
    with engine.begin() as connection:
        cfg = config(connection)
        command.upgrade(cfg, '0003')
        connection.execute(text("INSERT INTO users VALUES(1,'cart@example.test','Buyer','hash',0)"))
        connection.execute(text("INSERT INTO products(id,sku,title,description,category,price_kopecks,stock,active) VALUES(1,'cup','Cup','','home',100,5,1)"))
        connection.execute(text('INSERT INTO carts(id,user_id) VALUES(1,1)'))
        connection.execute(text('INSERT INTO cart_items(id,cart_id,product_id,quantity) VALUES(1,1,1,2)'))
        command.upgrade(cfg, 'head')
        assert connection.scalar(text('SELECT revision FROM carts')) == 0
        assert connection.scalar(text('SELECT quantity FROM cart_items')) == 2
        command.downgrade(cfg, '0003')
        assert connection.scalar(text('SELECT quantity FROM cart_items')) == 2
    engine.dispose()
