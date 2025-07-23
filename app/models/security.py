from app import db
from datetime import datetime

class BlockedIP(db.Model):
    __tablename__ = 'blocked_ips'
    __table_args__ = {'extend_existing': True}
    
    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(45), unique=True, nullable=False)  # 支持IPv6
    blocked_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    blocked_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    reason = db.Column(db.String(255))
    
    def __repr__(self):
        return f'<BlockedIP {self.ip_address}>'

class SecurityLog(db.Model):
    __tablename__ = 'security_logs'
    __table_args__ = {'extend_existing': True}
    
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    level = db.Column(db.String(20), nullable=False)  # info, warning, error
    module = db.Column(db.String(50), nullable=False)
    action = db.Column(db.String(50), nullable=False)
    message = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    ip_address = db.Column(db.String(45))
    details = db.Column(db.Text)
    
    user = db.relationship('User', backref=db.backref('security_logs', lazy=True))
    
    def __repr__(self):
        return f'<SecurityLog {self.action} {self.timestamp}>'

class LoginAttempt(db.Model):
    __tablename__ = 'login_attempts'
    __table_args__ = {'extend_existing': True}
    
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    ip_address = db.Column(db.String(45), nullable=False)
    username = db.Column(db.String(64))
    success = db.Column(db.Boolean, default=False)
    user_agent = db.Column(db.String(255))
    location = db.Column(db.String(100))
    
    def __repr__(self):
        return f'<LoginAttempt {self.ip_address} {self.success}>' 