"""Durable queue: HTTP enqueues only; a separate local worker owns inference."""
import sys
from datetime import timedelta
from pathlib import Path

from filelock import FileLock, Timeout
from flask import current_app
from models import db, AnalysisJob, MediaRecord, utcnow
from services.media import root, file_path


def available():
    return current_app.config['ML_ENABLED'] and Path(current_app.config['ML_WEIGHTS']).is_file()


def detector():
    if 'cash_detector' not in current_app.extensions:
        sys.path.insert(0, current_app.config['ML_ROOT'])
        from inference import Detector
        current_app.extensions['cash_detector'] = Detector(
            current_app.config['ML_WEIGHTS'], current_app.config['ML_DEVICE'])
    return current_app.extensions['cash_detector']


def expire_pending_api_jobs():
    """Do not spend inference time on API jobs whose queue deadline elapsed."""
    cutoff = utcnow() - timedelta(seconds=current_app.config['API_JOB_DEADLINE'])
    public_media = db.select(MediaRecord.id).where(MediaRecord.api_client_id.is_not(None))
    AnalysisJob.query.filter(AnalysisJob.media_id.in_(public_media),
        AnalysisJob.status == 'queued', AnalysisJob.created_at <= cutoff).update(
            dict(status='failed', error='API queue deadline exceeded.', finished_at=utcnow()),
            synchronize_session=False)
    db.session.commit()


def run_next_job():
    """One job under a shared filesystem lock, across workers and DB dialects."""
    if not available():
        raise RuntimeError('ML weights are unavailable or ML is disabled')
    try:
        with FileLock(str(root()/'.analysis-worker.lock'), timeout=0):
            expire_pending_api_jobs()
            # A crashed worker cannot leave its old job processing forever.
            stale = utcnow()-timedelta(seconds=current_app.config['ML_JOB_TIMEOUT']+90)
            AnalysisJob.query.filter(AnalysisJob.status == 'processing', AnalysisJob.started_at < stale).update(
                dict(status='failed', error='Обработка прервана. Повторите анализ.', finished_at=utcnow()),
                synchronize_session=False)
            db.session.commit()
            job = AnalysisJob.query.filter_by(status='queued').order_by(AnalysisJob.created_at, AnalysisJob.id).first()
            if not job:
                return None
            job.status, job.started_at, job.error = 'processing', utcnow(), None
            job_id = job.id
            db.session.commit()
            try:
                media = db.session.get(MediaRecord, job.media_id)
                result = detector().analyze(file_path(media.storage_key), root()/'analysis'/job_id,
                    job.camera_profile, current_app.config['ML_JOB_TIMEOUT'])
                job.result, job.status = result, 'done'
            except Exception as exc:
                db.session.rollback()
                job = db.session.get(AnalysisJob, job_id)
                current_app.logger.exception('Local analysis failed for job %s', job_id)
                job.status = 'failed'
                job.error = ('Профиль Forte Open требует видео 464×848. Выберите полный кадр.'
                    if isinstance(exc, ValueError) and 'forte_open requires' in str(exc)
                    else 'Не удалось обработать видео. Проверьте файл и журнал локального worker.')
            job.finished_at = utcnow()
            db.session.commit()
            db.session.remove()
            return job_id
    except Timeout:
        return None
