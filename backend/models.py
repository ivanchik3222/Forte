from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone
from uuid import uuid4

db = SQLAlchemy()


def _utc_iso(dt):
    """Convert datetime to ISO string with Z suffix for UTC."""
    if dt is None:
        return None
    return as_utc(dt).isoformat().replace('+00:00', 'Z')


def as_utc(dt):
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=True, index=True)
    nickname = db.Column(db.String(50), unique=True, nullable=True, index=True)
    password_hash = db.Column(db.String(255), nullable=True)

    full_name = db.Column(db.String(100))
    user_type = db.Column(db.String(20), default='user')  # user, admin
    is_active = db.Column(db.Boolean, default=True)
    is_verified = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_login = db.Column(db.DateTime)

    # Токены восстановления/верификации
    reset_token = db.Column(db.String(100), unique=True)
    reset_token_expires = db.Column(db.DateTime)
    verification_token = db.Column(db.String(100), unique=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    def to_dict(self, include_sensitive=False):
        data = {
            'id': self.id,
            'email': self.email,
            'nickname': self.nickname,
            'full_name': self.full_name,
            'user_type': self.user_type,
            'created_at': _utc_iso(self.created_at),
            'last_login': _utc_iso(self.last_login),
        }
        if include_sensitive:
            data['is_active'] = self.is_active
            data['is_verified'] = self.is_verified
        return data


def uid():
    return str(uuid4())


def utcnow():
    return datetime.now(timezone.utc)


class AuthSession(db.Model):
    __tablename__ = 'auth_sessions'
    id = db.Column(db.String(36), primary_key=True, default=uid)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    revoked_at = db.Column(db.DateTime(timezone=True))


class ApiClient(db.Model):
    """Retain the schema and ownership records from deployed migration 0006."""
    __tablename__ = 'api_clients'
    id = db.Column(db.String(36), primary_key=True, default=uid)
    key_hash = db.Column(db.String(64), nullable=False, unique=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    revoked_at = db.Column(db.DateTime(timezone=True))


class MediaRecord(db.Model):
    __tablename__ = 'media_records'
    id = db.Column(db.String(36), primary_key=True, default=uid)
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'), nullable=True)
    api_client_id = db.Column(db.String(36), db.ForeignKey('api_clients.id', ondelete='RESTRICT'), index=True)
    original_name = db.Column(db.String(255), nullable=False)
    search_name = db.Column(db.String(510), nullable=False, default=lambda context: context.get_current_parameters()['original_name'].casefold())
    storage_key = db.Column(db.String(80), nullable=False, unique=True)
    size_bytes = db.Column(db.BigInteger, nullable=False)
    content_type = db.Column(db.String(80), nullable=False)
    duration_sec = db.Column(db.Float)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    __table_args__ = (db.Index('ix_media_owner_created', 'owner_id', 'created_at', 'id'), db.CheckConstraint('size_bytes > 0', name='positive_media_size'),
        db.CheckConstraint('(owner_id IS NOT NULL AND api_client_id IS NULL) OR (owner_id IS NULL AND api_client_id IS NOT NULL)', name='media_exactly_one_owner'))

    def to_dict(self):
        job = AnalysisJob.query.filter_by(media_id=self.id).first()
        analysis_status = job.status if job else None
        result = job.result if job and job.status == 'done' and job.result else {}
        verdict = result.get('verdict') if result.get('rule_evaluation') == 'performed' else None
        findings = [dict(type=v['type'],timecode_sec=v['timecode_sec'],description=v['description'],rule=v['rule'],
                        classification_status=v.get('classification_status','grounded'))
                    for v in result.get('violations',[])] if verdict else []
        return dict(id=self.id, file_name=self.original_name, file_size=self.size_bytes,
                    duration_sec=self.duration_sec, created_at=_utc_iso(self.created_at),
                    status='stored', analysis_status=analysis_status or 'not_requested',
                    verdict=verdict, violations=findings)


class UploadRequest(db.Model):
    __tablename__ = 'upload_requests'
    id = db.Column(db.String(36), primary_key=True, default=uid)
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    key = db.Column(db.String(80), nullable=False)
    fingerprint = db.Column(db.String(64), nullable=False)
    media_id = db.Column(db.String(36), db.ForeignKey('media_records.id', ondelete='CASCADE'), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    __table_args__ = (db.UniqueConstraint('owner_id', 'key', name='uq_upload_owner_key'),)


class AnalysisJob(db.Model):
    __tablename__ = 'analysis_jobs'
    id = db.Column(db.String(36), primary_key=True, default=uid)
    media_id = db.Column(db.String(36), db.ForeignKey('media_records.id', ondelete='CASCADE'), nullable=False)
    camera_profile = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='queued')
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    started_at = db.Column(db.DateTime(timezone=True))
    finished_at = db.Column(db.DateTime(timezone=True))
    error = db.Column(db.Text)
    result = db.Column(db.JSON)
    __table_args__ = (
        db.UniqueConstraint('media_id', name='uq_analysis_media'),
        db.CheckConstraint("status in ('queued','processing','done','failed')", name='analysis_status'),
        db.CheckConstraint("camera_profile in ('forte_open','full_frame')", name='analysis_camera_profile'),
        db.Index('ix_analysis_status_created', 'status', 'created_at'),
    )


class Camera(db.Model):
    __tablename__ = 'cameras'
    id = db.Column(db.String(36), primary_key=True, default=uid)
    name = db.Column(db.String(120), nullable=False)
    location = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='unknown')
    last_seen_at = db.Column(db.DateTime(timezone=True))
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    __table_args__ = (db.CheckConstraint("status in ('unknown','online','offline')", name='camera_status'),)

    def to_dict(self):
        return dict(id=self.id, name=self.name, location=self.location, status=self.status, last_seen_at=_utc_iso(self.last_seen_at), is_active=self.is_active)


class CameraAlert(db.Model):
    __tablename__ = 'camera_alerts'
    id = db.Column(db.String(36), primary_key=True, default=uid)
    camera_id = db.Column(db.String(36), db.ForeignKey('cameras.id', ondelete='RESTRICT'), nullable=False)
    source = db.Column(db.String(80), nullable=False)
    external_event_id = db.Column(db.String(120))
    detected_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    type = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=False)
    timecode_sec = db.Column(db.Float, nullable=False, default=0)
    rule = db.Column(db.JSON)
    camera = db.relationship(Camera)
    __table_args__ = (db.UniqueConstraint('source', 'external_event_id', name='uq_alert_source_external'), db.Index('ix_alert_camera_detected', 'camera_id', 'detected_at', 'id'), db.CheckConstraint('timecode_sec >= 0', name='positive_timecode'))


class AlertRead(db.Model):
    __tablename__ = 'alert_reads'
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    alert_id = db.Column(db.String(36), db.ForeignKey('camera_alerts.id', ondelete='CASCADE'), primary_key=True)
    read_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


class AlertRecording(db.Model):
    __tablename__ = 'alert_recordings'
    alert_id = db.Column(db.String(36), db.ForeignKey('camera_alerts.id', ondelete='CASCADE'), primary_key=True)
    media_id = db.Column(db.String(36), db.ForeignKey('media_records.id', ondelete='RESTRICT'), nullable=False, index=True)


class CameraHealthReport(db.Model):
    __tablename__ = 'camera_health_reports'
    id = db.Column(db.String(36), primary_key=True, default=uid)
    camera_id = db.Column(db.String(36), db.ForeignKey('cameras.id', ondelete='CASCADE'), nullable=False)
    external_id = db.Column(db.String(120), nullable=False)
    source = db.Column(db.String(80), nullable=False)
    status = db.Column(db.String(20), nullable=False)
    checked_at = db.Column(db.DateTime(timezone=True), nullable=False)
    received_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    __table_args__ = (
        db.UniqueConstraint('camera_id', 'external_id', name='uq_health_camera_external'),
        db.Index('ix_health_camera_checked', 'camera_id', 'checked_at'),
        db.CheckConstraint("status in ('observing','offline','occluded','frozen','poor_visibility')", name='health_report_status'),
    )


class CameraHealthInterval(db.Model):
    __tablename__ = 'camera_health_intervals'
    id = db.Column(db.String(36), primary_key=True, default=uid)
    camera_id = db.Column(db.String(36), db.ForeignKey('cameras.id', ondelete='CASCADE'), nullable=False)
    kind = db.Column(db.String(20), nullable=False)
    started_at = db.Column(db.DateTime(timezone=True), nullable=False)
    ended_at = db.Column(db.DateTime(timezone=True))
    __table_args__ = (
        db.Index('ix_health_interval_camera_start', 'camera_id', 'started_at'),
        db.CheckConstraint("kind in ('offline','occluded','frozen','poor_visibility','unknown')", name='health_interval_kind'),
        db.CheckConstraint('ended_at IS NULL OR ended_at >= started_at', name='health_interval_order'),
    )


class EvidenceFrame(db.Model):
    __tablename__ = 'evidence_frames'
    id = db.Column(db.String(36), primary_key=True, default=uid)
    alert_id = db.Column(db.String(36), db.ForeignKey('camera_alerts.id', ondelete='CASCADE'), nullable=False, index=True)
    timestamp_sec = db.Column(db.Float, nullable=False)
    storage_key = db.Column(db.String(80), nullable=False, unique=True)


class RegulatorySource(db.Model):
    __tablename__ = 'regulatory_sources'
    id = db.Column(db.String(36), primary_key=True, default=uid)
    title = db.Column(db.Text, nullable=False)
    number = db.Column(db.String(80))
    document_date = db.Column(db.String(10))
    url = db.Column(db.Text, nullable=False, unique=True)
    publisher = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    def to_dict(self):
        return {k: getattr(self, k) for k in ('id', 'title', 'number', 'document_date', 'url', 'publisher')}


class Branch(db.Model):
    __tablename__ = 'branches'
    id = db.Column(db.String(36), primary_key=True, default=uid)
    name = db.Column(db.String(120), nullable=False)


class CameraScope(db.Model):
    __tablename__ = 'camera_scopes'
    camera_id = db.Column(db.String(36), db.ForeignKey('cameras.id', ondelete='CASCADE'), primary_key=True)
    branch_id = db.Column(db.String(36), db.ForeignKey('branches.id', ondelete='RESTRICT'), nullable=False)
    is_demo = db.Column(db.Boolean, nullable=False, default=False)


class BranchAccess(db.Model):
    __tablename__ = 'branch_access'
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    branch_id = db.Column(db.String(36), db.ForeignKey('branches.id', ondelete='CASCADE'), primary_key=True)


class CameraAccess(db.Model):
    __tablename__ = 'camera_access'
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    camera_id = db.Column(db.String(36), db.ForeignKey('cameras.id', ondelete='CASCADE'), primary_key=True)


class SessionSecurity(db.Model):
    __tablename__ = 'session_security'
    session_id = db.Column(db.String(36), db.ForeignKey('auth_sessions.id', ondelete='CASCADE'), primary_key=True)
    refresh_jti = db.Column(db.String(36), nullable=False)
    mfa_verified = db.Column(db.Boolean, nullable=False, default=False)


class LoginBucket(db.Model):
    __tablename__ = 'login_buckets'
    key = db.Column(db.String(64), primary_key=True)
    window = db.Column(db.BigInteger, nullable=False)
    count = db.Column(db.Integer, nullable=False)


class UserMFA(db.Model):
    __tablename__ = 'user_mfa'
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    secret = db.Column(db.Text, nullable=False)
    last_step = db.Column(db.BigInteger, nullable=False, default=-1)
