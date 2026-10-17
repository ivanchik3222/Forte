import json
import time
from pathlib import Path
import click
from flask import current_app
from flask_migrate import upgrade, stamp
from sqlalchemy import inspect, MetaData
from alembic.migration import MigrationContext
from alembic.autogenerate import compare_metadata
from models import db, User, MediaRecord, EvidenceFrame, Camera, CameraAlert, RegulatorySource, uid, utcnow, as_utc
from services.demo_account import DEMO_EMAIL, seed_demo_user


def register_cli(app):
    @app.cli.command('analysis-worker')
    @click.option('--once', is_flag=True, help='Process at most one queued job and exit.')
    def analysis_worker(once):
        """Run the local ML queue in a separate process using the ML environment."""
        from services.analysis import run_next_job, detector, available
        if not available():
            raise click.ClickException('Local weights missing or ML disabled.')
        detector()  # Fail at startup on missing ML dependencies or incompatible weights.
        while True:
            job_id = run_next_job()
            if job_id:
                click.echo(f'Completed job {job_id}')
            if once:
                break
            if not job_id:
                db.session.remove()
                time.sleep(1)

    @app.cli.command('init-db')
    def init_db():
        """Apply versioned migrations to an empty or already versioned database."""
        upgrade()
        seed_demo_user()

    @app.cli.command('adopt-legacy-db')
    @click.option('--backup-confirmed', is_flag=True, required=True, help='Confirm a restorable backup exists.')
    def adopt_legacy_db(backup_confirmed):
        """Verify the exact legacy users-only schema before stamping baseline."""
        inspector = inspect(db.engine)
        tables = set(inspector.get_table_names())
        if tables != {'users'}:
            raise click.ClickException('Expected only the legacy users table. No changes made.')
        if inspector.get_pk_constraint('users')['constrained_columns'] != ['id'] or inspector.get_foreign_keys('users') or inspector.get_check_constraints('users'):
            raise click.ClickException('Legacy constraints differ from baseline. No changes made.')
        expected = MetaData()
        User.__table__.to_metadata(expected)
        with db.engine.connect() as connection:
            differences = compare_metadata(MigrationContext.configure(connection, opts={'compare_server_default': True}), expected)
        if differences:
            raise click.ClickException(f'Legacy schema differs from baseline: {differences}. No changes made.')
        stamp(revision='0001')
        upgrade()
        click.echo('Legacy schema adopted; users preserved.')

    @app.cli.command('create-user')
    @click.option('--email', prompt=True)
    @click.option('--password', prompt=True, hide_input=True, confirmation_prompt=True)
    @click.option('--admin', is_flag=True)
    def create_user(email, password, admin):
        from routes.auth import validate_email
        email = email.strip().lower()
        if email == DEMO_EMAIL:
            raise click.ClickException('This email is reserved. Use seed-demo-user.')
        if not validate_email(email) or len(password) < 8:
            raise click.ClickException('Valid email and password of at least 8 characters required.')
        if User.query.filter_by(email=email).first():
            raise click.ClickException('User already exists.')
        user = User(email=email, full_name=email.split('@')[0], user_type='admin' if admin else 'user', is_active=True)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f'Created {email}')

    @app.cli.command('seed-demo-user')
    def seed_demo_account():
        """Ensure the shared, non-admin demo account exists without resetting its data."""
        try:
            user = seed_demo_user()
        except ValueError as exc:
            raise click.ClickException(str(exc)) from exc
        click.echo(f'Demo account available: {user.email}')

    @app.cli.command('seed-sources')
    def seed_sources():
        url = 'https://adilet.zan.kz/rus/docs/V1900019680'
        if not RegulatorySource.query.filter_by(url=url).first():
            db.session.add(RegulatorySource(title='Правила осуществления кассовых операций и операций по инкассации банкнот, монет и ценностей',
                                           number='Постановление Правления НБРК № 231', document_date='2019-11-29', url=url, publisher='Национальный Банк РК'))
            db.session.commit()
        click.echo('Reference source available. Applicability has not been verified.')

    @app.cli.command('import-test-events')
    @click.argument('fixture', type=click.Path(exists=True, path_type=Path))
    def import_test_events(fixture):
        """Import explicit test events; never called on application startup."""
        if not (app.debug or app.testing or app.config['ALLOW_TEST_EVENTS']):
            raise click.ClickException('Test events disabled in production.')
        from datetime import datetime
        from services.media import root
        import shutil
        data = json.loads(fixture.read_text(encoding='utf-8'))
        created_files = []
        try:
            for row in data:
                if CameraAlert.query.filter_by(source='test', external_event_id=row['id']).first():
                    continue
                camera = db.session.get(Camera, row['camera_id'])
                if camera is None:
                    camera = Camera(id=row['camera_id'], name=row['camera_name'], location=row['location'])
                    db.session.add(camera)
                    db.session.flush()
                detected = datetime.fromisoformat(row['detected_at'].replace('Z', '+00:00')) if row.get('detected_at') else utcnow()
                if detected.tzinfo is None:
                    raise ValueError('detected_at requires timezone')
                alert = CameraAlert(id=uid(), camera_id=camera.id, source='test', external_event_id=row['id'], detected_at=as_utc(detected),
                                    type=row['type'], description=row['description'], timecode_sec=row.get('timecode_sec', 0))
                db.session.add(alert)
                db.session.flush()
                for frame in row.get('frames', []):
                    source = (fixture.parent / frame['path']).resolve()
                    if source.parent != fixture.parent.resolve() or source.read_bytes()[:3] != b'\xff\xd8\xff':
                        raise ValueError('Expected a JPEG next to the fixture')
                    key = uid() + '.jpg'
                    target = root() / key
                    shutil.copyfile(source, target)
                    created_files.append(target)
                    db.session.add(EvidenceFrame(alert_id=alert.id, timestamp_sec=frame['timestamp_sec'], storage_key=key))
            db.session.commit()
        except Exception:
            db.session.rollback()
            for path in created_files:
                path.unlink(missing_ok=True)
            raise
        click.echo('Test events imported with source=test.')

    @app.cli.command('cleanup-media')
    @click.option('--apply', 'apply_changes', is_flag=True, help='Delete orphan files older than 24 hours; default is a dry run.')
    def cleanup_media(apply_changes):
        from services.media import root
        known = {x[0] for x in db.session.query(MediaRecord.storage_key)} | {x[0] for x in db.session.query(EvidenceFrame.storage_key)}
        for path in root().iterdir():
            if path.is_symlink() or not path.is_file() or path.name.endswith('.lock'):
                continue
            if path.name not in known and path.stat().st_mtime < time.time() - 86400:
                click.echo(path.name)
                if apply_changes:
                    path.unlink()
