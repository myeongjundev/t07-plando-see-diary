import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from sqlalchemy.exc import SQLAlchemyError

from app import create_app
from app.extensions import db
from test_card2_tasks import create_plan, create_task, PLAN
from test_card3_executions import LOG
from test_card4_see import REFLECTION, NEXT

SCHEMA = json.loads((Path(__file__).parents[3] / 'contracts/pds-schema-v2.json').read_text(encoding='utf-8'))
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())


def test_t06_c36_complete_export_retains_deleted_history_and_links(client):
    plan = create_plan(client)
    assert client.patch(f"/api/plans/{plan['id']}", json={**PLAN, 'title': '합성 수정'}).status_code == 200
    task = create_task(client, plan['id'], content='<script>window.__xss=1</script>')
    log = client.post(f"/api/tasks/{task['id']}/executions", json=LOG).json['execution']
    assert client.post(f"/api/tasks/{task['id']}/complete", json={'idempotencyKey': 'card5-export-key'}).status_code == 200
    reflection = client.post(f"/api/plans/{plan['id']}/reflections", json=REFLECTION).json['reflection']
    next_plan = client.post(f"/api/reflections/{reflection['id']}/next-plan", json=NEXT).json['plan']
    assert client.delete(f"/api/tasks/{task['id']}").status_code == 204
    response = client.get('/api/export')
    assert response.status_code == 200
    assert response.headers['Content-Disposition'] == 'attachment; filename="t06-diary-v2.json"'
    assert response.headers['Cache-Control'] == 'no-store'
    data = response.json
    VALIDATOR.validate(data)
    assert [len(data[k]) for k in ['plans', 'planRevisions', 'tasks', 'taskTags', 'completionEvents', 'executionLogs', 'reflections']] == [2, 1, 1, 2, 1, 1, 1]
    assert data['tasks'][0]['content'] == task['content']
    assert data['tasks'][0]['deletedAt'] and data['tasks'][0]['completedAt']
    assert data['executionLogs'] == [log]
    assert data['completionEvents'][0]['taskId'] == task['id']
    assert data['reflections'][0]['nextPlanId'] == next_plan['id']
    assert data['planRevisions'][0]['title'] == plan['title']
    # Every table is accounted for as either diary data or deliberately withheld.
    # A new table has to be classified before this passes, so the way T07 adds a
    # credentials table is never "and it quietly joined the export".
    withheld = SCHEMA['database']['nonExportedTables']
    exported = SCHEMA['database']['tables']
    assert set(db.metadata.tables) == set(exported) | set(withheld)
    assert not set(exported) & set(withheld)
    for table_name, table in db.metadata.tables.items():
        if table_name in withheld:
            continue
        mapping = exported[table_name]['fields']
        assert set(mapping) == set(table.columns.keys())
        export_name = table_name.split('_')[0] + ''.join(s.title() for s in table_name.split('_')[1:])
        published = {field['exportField'] for field in mapping.values() if field['exportField']}
        withheld_fields = {name for name, field in mapping.items() if not field['exportField']}
        for row in data[export_name]:
            assert published <= row.keys()
            # A column marked unexported must actually be absent, under either
            # spelling -- the contract is only worth the check behind it.
            assert not withheld_fields & row.keys()
            camel = {n.split('_')[0] + ''.join(s.title() for s in n.split('_')[1:]) for n in withheld_fields}
            assert not camel & row.keys()
    # Nothing from a withheld table may ride along under any key.
    assert not {t for t in withheld} & data.keys()
    serialized = json.dumps(data)
    for secret_field in ('password_hash', 'passwordHash', 'token_sha256', 'tokenSha256', 'ip_hash', 'ipHash'):
        assert secret_field not in serialized
    again = client.get('/api/export').json
    assert {k: v for k, v in again.items() if k != 'exportedAt'} == {k: v for k, v in data.items() if k != 'exportedAt'}


def test_empty_export_is_valid(client):
    VALIDATOR.validate(client.get('/api/export').json)


def test_database_error_does_not_expose_exception(client, monkeypatch, caplog):
    def fail(*args, **kwargs):
        raise SQLAlchemyError('synthetic-private-credential')
    monkeypatch.setattr(db.session, 'execute', fail)
    response = client.get('/api/health')
    assert response.status_code == 503
    assert 'synthetic-private-credential' not in response.text + caplog.text


def test_hosting_probe_does_not_query_or_wake_database(client, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Hosting liveness must not touch the database')
    monkeypatch.setattr(db.session, 'execute', forbidden)
    monkeypatch.setattr(db.engine, 'connect', forbidden)
    response = client.get('/api/live')
    assert response.status_code == 200
    assert response.json == {'status': 'ok'}


def test_production_requires_postgres_and_serves_static_with_csp(tmp_path):
    with pytest.raises(RuntimeError, match='PostgreSQL'):
        create_app({'REQUIRE_POSTGRES': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://'})
    (tmp_path / 'index.html').write_text('<html>synthetic build</html>', encoding='utf-8')
    app = create_app({'TESTING': True, 'STATIC_DIST': str(tmp_path), 'SQLALCHEMY_DATABASE_URI': 'sqlite://'})
    client = app.test_client()
    response = client.get('/')
    assert response.status_code == 200 and 'synthetic build' in response.text
    assert "script-src 'self'" in response.headers['Content-Security-Policy']
    assert 'unsafe-inline' not in response.headers['Content-Security-Policy']
    assert client.get('/assets/../../pyproject.toml').status_code == 404
    assert client.get('/.env').status_code == 404


def test_installed_production_app_uses_explicit_frontend_path(tmp_path, monkeypatch):
    monkeypatch.setenv('STATIC_DIST', str(tmp_path))
    production = {'TESTING': True, 'REQUIRE_POSTGRES': True,
                  'SQLALCHEMY_DATABASE_URI': 'postgresql+psycopg://localhost/unused'}
    with pytest.raises(RuntimeError, match='frontend build is missing'):
        create_app(production)
    (tmp_path / 'index.html').write_text('<html>synthetic production build</html>', encoding='utf-8')
    assets = tmp_path / 'assets'
    assets.mkdir()
    (assets / 'main.js').write_text('/* synthetic bundle */', encoding='utf-8')
    app = create_app(production)
    client = app.test_client()
    assert client.get('/').status_code == 200
    assert 'synthetic production build' in client.get('/').text
    assert client.get('/assets/main.js').status_code == 200
    assert client.get('/api/live').status_code == 200
    with app.app_context():
        db.engine.dispose()
