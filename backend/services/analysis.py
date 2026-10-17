"""Durable queue: HTTP enqueues only; a separate local worker owns inference."""
import sys
from datetime import timedelta
from pathlib import Path

from filelock import FileLock, Timeout
from flask import current_app
from models import db, AnalysisJob, MediaRecord, utcnow
from services.media import root, file_path
from utils.errors import ApiError


def available():
    if not current_app.config['ML_ENABLED']:
        return False
    engine = current_app.config.get('ML_ENGINE', 'objects')
    if engine in ('reviewed_pipeline', 'reviewed_temporal'):
        bundle = Path(current_app.config['ML_REVIEWED_BUNDLE'])
        if not (bundle.is_file() and (bundle.parent/'bank_only.npz').is_file() and
                Path(current_app.config['ML_REVIEWED_BACKBONE']).is_file() and
                Path(current_app.config['ML_REVIEWED_PYTHON']).is_file()):
            return False
        if engine == 'reviewed_temporal':
            return True
    if engine in ('dense_vlm', 'reviewed_pipeline'):
        size = current_app.config.get('ML_VLM_MODEL_SIZE', '4b')
        if size not in ('4b', '8b') or current_app.config.get('ML_VLM_INPUT_MODE', 'images') not in ('images', 'native_video'):
            return False
        names = ['model.safetensors'] if size == '4b' else ['model-00001-of-00002.safetensors', 'model-00002-of-00002.safetensors']
        return (Path(current_app.config['ML_VLM_PYTHON']).is_file() and
            all((Path(current_app.config['ML_ROOT'])/f'models/qwen3_vl_{size}_mlx'/name).is_file() for name in names) and
            (not current_app.config.get('ML_VLM_ADAPTER') or
             (Path(current_app.config['ML_VLM_ADAPTER'])/'adapters.safetensors').is_file()))
    return engine == 'objects' and Path(current_app.config['ML_WEIGHTS']).is_file()


def detector():
    engine = current_app.config.get('ML_ENGINE', 'objects')
    if engine in ('dense_vlm', 'reviewed_pipeline'):
        if 'caption_analyzer' not in current_app.extensions:
            sys.path.insert(0, current_app.config['ML_ROOT'])
            from caption_worker import CaptionAnalyzer
            current_app.extensions['caption_analyzer'] = CaptionAnalyzer(
                current_app.config['ML_VLM_PYTHON'], current_app.config['ML_ROOT'],
                current_app.config.get('ML_VLM_ADAPTER'), current_app.config.get('ML_VLM_MODEL_SIZE', '4b'),
                current_app.config.get('ML_VLM_INPUT_MODE', 'images'),assess_rules=engine == 'reviewed_pipeline')
        if engine == 'dense_vlm':
            return current_app.extensions['caption_analyzer']
    if engine in ('reviewed_temporal', 'reviewed_pipeline'):
        if 'reviewed_analyzer' not in current_app.extensions:
            sys.path.insert(0, current_app.config['ML_ROOT'])
            from reviewed_pipeline import ReviewedPipeline
            current_app.extensions['reviewed_analyzer'] = ReviewedPipeline(
                current_app.config['ML_REVIEWED_PYTHON'], current_app.config['ML_ROOT'],
                current_app.config['ML_REVIEWED_BUNDLE'], current_app.config['ML_REVIEWED_BACKBONE'],
                current_app.config.get('ML_DEVICE'),
                current_app.extensions.get('caption_analyzer') if engine == 'reviewed_pipeline' else None)
        return current_app.extensions['reviewed_analyzer']
    if 'cash_detector' not in current_app.extensions:
        sys.path.insert(0, current_app.config['ML_ROOT'])
        from inference import Detector
        current_app.extensions['cash_detector'] = Detector(
            current_app.config['ML_WEIGHTS'], current_app.config['ML_DEVICE'])
    return current_app.extensions['cash_detector']


def enqueue_job(media_id, profile='forte_open', retry_failed=True, require_idle=False):
    """Shared durable enqueue for multipart upload and explicit retries."""
    if not available():
        raise ApiError(503, 'analysis_unavailable', 'Локальная модель не установлена или отключена.')
    try:
        with FileLock(str(root()/'.analysis-submit.lock'), timeout=0):
            job = AnalysisJob.query.filter_by(media_id=media_id).first()
            if job and (job.status != 'failed' or not retry_failed):
                if job.camera_profile != profile:
                    raise ApiError(409, 'profile_conflict', 'Для записи уже выполнялся анализ с другим профилем.')
                return job, 200
            active = AnalysisJob.query.filter(AnalysisJob.status.in_(['queued', 'processing'])).count()
            if (require_idle and active) or active >= current_app.config['ML_QUEUE_LIMIT']:
                raise ApiError(429, 'analysis_busy', 'Очередь заполнена. Повторите позже.')
            if job:
                job.status, job.camera_profile, job.result, job.error = 'queued', profile, None, None
                job.created_at, job.started_at, job.finished_at = utcnow(), None, None
            else:
                job = AnalysisJob(media_id=media_id, camera_profile=profile)
                db.session.add(job)
            db.session.commit()
            return job, 202
    except Timeout:
        raise ApiError(429, 'analysis_busy', 'Повторите запрос через несколько секунд.')


def run_next_job():
    """One job under a shared filesystem lock, across workers and DB dialects."""
    if not available():
        raise RuntimeError('ML weights are unavailable or ML is disabled')
    try:
        with FileLock(str(root()/'.analysis-worker.lock'), timeout=0):
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
