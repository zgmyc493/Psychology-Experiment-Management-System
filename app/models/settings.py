from app import db
from datetime import datetime

class SystemSetting(db.Model):
    __tablename__ = 'system_settings'
    __table_args__ = {'extend_existing': True}
    
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(255), nullable=False, unique=True)
    value = db.Column(db.String(255))
    description = db.Column(db.String(255))
    
    # 安全设置
    two_factor_auth = db.Column(db.Boolean, default=False)
    password_expiry_days = db.Column(db.Integer, default=90)
    max_login_attempts = db.Column(db.Integer, default=5)
    
    # 邮件设置
    smtp_server = db.Column(db.String(255))
    smtp_port = db.Column(db.Integer)
    smtp_username = db.Column(db.String(255))
    smtp_password = db.Column(db.String(255))
    sender_email = db.Column(db.String(255))
    
    # 系统维护
    last_backup = db.Column(db.DateTime)
    last_cleanup = db.Column(db.DateTime)
    
    # 时间戳
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return '<SystemSetting %r>' % self.key 