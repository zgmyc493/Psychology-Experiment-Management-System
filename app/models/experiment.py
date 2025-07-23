from datetime import datetime
from app import db
import random
import string

class Experiment(db.Model):
    __tablename__ = 'experiments'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(128), nullable=False)
    description = db.Column(db.Text)
    duration = db.Column(db.String(64))
    reward = db.Column(db.String(64))
    status = db.Column(db.String(32), default='draft')  # draft, active, completed, cancelled
    visibility = db.Column(db.String(32), default='private')  # private(仅邀请), public(公开), invitecode(仅邀请码)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    creator_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    invite_code = db.Column(db.String(8), unique=True)  # 邀请码
    deleted_at = db.Column(db.DateTime, nullable=True)  # 软删除时间
    deleted_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # 删除者ID
    
    # 新增字段
    categories = db.Column(db.PickleType, default=list)  # 实验类别
    min_age = db.Column(db.Integer, nullable=True)  # 最小年龄要求
    max_age = db.Column(db.Integer, nullable=True)  # 最大年龄要求
    required_gender = db.Column(db.String(16), default='any')  # 性别要求：any, male, female
    requirements = db.Column(db.Text, nullable=True)  # 其他要求
    max_participants = db.Column(db.Integer, nullable=True)  # 最大参与人数
    auto_close = db.Column(db.Boolean, default=False)  # 是否达到人数上限自动关闭
    external_url = db.Column(db.String(256), nullable=True)  # 外部实验链接
    auto_approve = db.Column(db.Boolean, default=False)  # 是否自动批准申请
    send_reminder = db.Column(db.Boolean, default=True)  # 是否发送参与提醒
    allow_withdrawal = db.Column(db.Boolean, default=True)  # 是否允许中途退出
    notes = db.Column(db.Text, nullable=True)  # 管理员备注
    
    # 自动开启实验相关
    scheduled_start_time = db.Column(db.DateTime, nullable=True)  # 计划开始时间
    
    # 关系
    participations = db.relationship('Participation',
                                   backref=db.backref('experiment', lazy='joined'),
                                   lazy='dynamic',
                                   cascade='all, delete-orphan')
    
    invitations = db.relationship('ExperimentInvitation',
                                backref=db.backref('experiment', lazy='joined'),
                                lazy='dynamic',
                                cascade='all, delete-orphan')

    deleted_by = db.relationship('User',
                               foreign_keys=[deleted_by_id],
                               backref=db.backref('deleted_experiments', lazy='dynamic'))

    def __init__(self, *args, **kwargs):
        super(Experiment, self).__init__(*args, **kwargs)
        if not self.invite_code:
            self.generate_invite_code()
            
    def generate_invite_code(self):
        """生成唯一的8位邀请码"""
        while True:
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            if not Experiment.query.filter_by(invite_code=code).first():
                self.invite_code = code
                break

    def soft_delete(self, user_id):
        """软删除实验"""
        self.deleted_at = datetime.utcnow()
        self.deleted_by_id = user_id
        self.status = 'cancelled'  # 将实验状态设为已取消

    def restore(self):
        """恢复已删除的实验"""
        self.deleted_at = None
        self.deleted_by_id = None
        self.status = 'draft'  # 恢复为草稿状态

    @property
    def is_deleted(self):
        """判断实验是否已删除"""
        return self.deleted_at is not None

    @property
    def is_scheduled(self):
        """检查实验是否设置了计划开始时间"""
        return self.scheduled_start_time is not None
    
    @property
    def should_auto_start(self):
        """检查实验是否应该自动开始"""
        if not self.is_scheduled:
            return False
        if self.status != 'draft':
            return False
        return self.scheduled_start_time <= datetime.utcnow()

    def __repr__(self):
        return f'<Experiment {self.title}>'

class Participation(db.Model):
    __tablename__ = 'participations'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    experiment_id = db.Column(db.Integer, db.ForeignKey('experiments.id'), nullable=False)
    status = db.Column(db.String(32), default='pending')  # pending, started, completed, dropped
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<Participation {self.user_id}:{self.experiment_id}>'

class ExperimentInvitation(db.Model):
    __tablename__ = 'experiment_invitations'
    
    id = db.Column(db.Integer, primary_key=True)
    experiment_id = db.Column(db.Integer, db.ForeignKey('experiments.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    status = db.Column(db.String(32), default='pending')  # pending, accepted, rejected, expired
    invited_at = db.Column(db.DateTime, default=datetime.utcnow)
    responded_at = db.Column(db.DateTime)
    response_note = db.Column(db.String(256))  # 用户回复的备注

    def accept(self, note=None):
        """接受邀请"""
        self.status = 'accepted'
        self.responded_at = datetime.utcnow()
        self.response_note = note
        
        # 创建参与记录
        participation = Participation(
            experiment_id=self.experiment_id,
            user_id=self.user_id,
            status='pending'
        )
        db.session.add(participation)
        return True

    def reject(self, note=None):
        """拒绝邀请"""
        self.status = 'rejected'
        self.responded_at = datetime.utcnow()
        self.response_note = note
        return True

    def cancel(self):
        """管理员取消邀请"""
        if self.status == 'pending':
            self.status = 'cancelled'
            self.responded_at = datetime.utcnow()
            return True
        return False

    @property
    def status_display(self):
        """获取状态的显示文本"""
        status_map = {
            'pending': '待回应',
            'accepted': '已接受',
            'rejected': '已拒绝',
            'expired': '已过期',
            'cancelled': '已取消'
        }
        return status_map.get(self.status, self.status)

    def __repr__(self):
        return f'<ExperimentInvitation {self.user_id}:{self.experiment_id}>'

class ExperimentReservation(db.Model):
    """实验预约模型 - 用于用户预约未开始的公开实验"""
    __tablename__ = 'experiment_reservations'
    
    id = db.Column(db.Integer, primary_key=True)
    experiment_id = db.Column(db.Integer, db.ForeignKey('experiments.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    reserved_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(32), default='pending')  # pending, auto_joined, cancelled
    joined_at = db.Column(db.DateTime, nullable=True)  # 自动加入时间
    
    # 关系
    experiment = db.relationship('Experiment', backref=db.backref('reservations', lazy='dynamic'))
    user = db.relationship('User', backref=db.backref('experiment_reservations', lazy='dynamic'))
    
    def auto_join(self):
        """实验开始招募后自动加入"""
        self.status = 'auto_joined'
        self.joined_at = datetime.utcnow()
        
        # 创建参与记录
        participation = Participation(
            experiment_id=self.experiment_id,
            user_id=self.user_id,
            status='pending',
            started_at=datetime.utcnow(),  # 设置开始时间
            updated_at=datetime.utcnow()   # 设置更新时间
        )
        db.session.add(participation)
        return participation
    
    def cancel(self):
        """取消预约"""
        self.status = 'cancelled'
        return True
    
    def __repr__(self):
        return f'<ExperimentReservation {self.user_id}:{self.experiment_id}>' 