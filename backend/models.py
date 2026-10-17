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


class MediaRecord(db.Model):
    __tablename__ = 'media_records'
    id = db.Column(db.String(36), primary_key=True, default=uid)
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False)
    original_name = db.Column(db.String(255), nullable=False)
    search_name = db.Column(db.String(510), nullable=False, default=lambda context: context.get_current_parameters()['original_name'].casefold())
    storage_key = db.Column(db.String(80), nullable=False, unique=True)
    size_bytes = db.Column(db.BigInteger, nullable=False)
    content_type = db.Column(db.String(80), nullable=False)
    duration_sec = db.Column(db.Float)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    __table_args__ = (db.Index('ix_media_owner_created', 'owner_id', 'created_at', 'id'), db.CheckConstraint('size_bytes > 0', name='positive_media_size'))

    def to_dict(self):
        return dict(id=self.id, file_name=self.original_name, file_size=self.size_bytes,
                    duration_sec=self.duration_sec, created_at=_utc_iso(self.created_at),
                    status='stored', analysis_status='not_requested', verdict=None, violations=[])


class UploadRequest(db.Model):
    __tablename__ = 'upload_requests'
    id = db.Column(db.String(36), primary_key=True, default=uid)
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    key = db.Column(db.String(80), nullable=False)
    fingerprint = db.Column(db.String(64), nullable=False)
    media_id = db.Column(db.String(36), db.ForeignKey('media_records.id', ondelete='CASCADE'), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    __table_args__ = (db.UniqueConstraint('owner_id', 'key', name='uq_upload_owner_key'),)


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
