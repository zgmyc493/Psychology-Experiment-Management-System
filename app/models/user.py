from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from app.extensions import db, login_manager
from datetime import datetime
import pytz

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, index=True)
    email = db.Column(db.String(120), unique=True, index=True)
    password_hash = db.Column(db.String(128))
    role = db.Column(db.String(32), default='participant')  # superadmin, admin or participant
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)
    last_password_change = db.Column(db.DateTime, default=datetime.utcnow)
    
    # 新增的个人信息字段
    gender = db.Column(db.String(10))  # 性别：male/female
    age = db.Column(db.Integer)  # 年龄
    graduation_date = db.Column(db.Date)  # 毕业时间
    phone = db.Column(db.String(20))  # 电话号码
    school = db.Column(db.String(100))  # 学校
    college = db.Column(db.String(100))  # 学院
    profile_completed = db.Column(db.Boolean, default=False)  # 是否完成个人信息维护

    # 关系
    created_experiments = db.relationship('Experiment', 
                                        foreign_keys='Experiment.creator_id',
                                        backref=db.backref('creator', lazy='joined'),
                                        lazy='dynamic')
    
    participations = db.relationship('Participation',
                                   foreign_keys='Participation.user_id',
                                   backref=db.backref('user', lazy='joined'),
                                   lazy='dynamic',
                                   cascade='all, delete-orphan')
    
    participated_experiments = db.relationship('Experiment',
                                            secondary='participations',
                                            primaryjoin='User.id==Participation.user_id',
                                            secondaryjoin='Participation.experiment_id==Experiment.id',
                                            backref=db.backref('participants', lazy='dynamic'),
                                            lazy='dynamic',
                                            overlaps="participations,user")
    
    # 收到的邀请
    received_invitations = db.relationship('ExperimentInvitation',
                                         foreign_keys='ExperimentInvitation.user_id',
                                         backref=db.backref('user', lazy='joined'),
                                         lazy='dynamic',
                                         cascade='all, delete-orphan')
    
    # 发出的邀请（管理员）
    sent_invitations = db.relationship('ExperimentInvitation',
                                     foreign_keys='ExperimentInvitation.created_by_id',
                                     backref=db.backref('created_by', lazy='joined'),
                                     lazy='dynamic',
                                     cascade='all, delete-orphan')

    def __init__(self, **kwargs):
        super(User, self).__init__(**kwargs)
        if self.role is None:
            self.role = 'participant'
        # 如果尝试创建超级管理员，检查是否已存在
        if self.role == 'superadmin' and User.query.filter_by(role='superadmin').first() is not None:
            raise ValueError('系统中已存在超级管理员，不能创建第二个超级管理员')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        self.last_password_change = datetime.utcnow()

    def verify_password(self, password):
        return check_password_hash(self.password_hash, password)

    def update_last_login(self):
        self.last_login = datetime.utcnow()

    @property
    def local_created_at(self):
        if self.created_at:
            return self.created_at.replace(tzinfo=pytz.UTC).astimezone(pytz.timezone('Asia/Shanghai'))
        return None

    @property
    def local_last_login(self):
        if self.last_login:
            return self.last_login.replace(tzinfo=pytz.UTC).astimezone(pytz.timezone('Asia/Shanghai'))
        return None

    def __repr__(self):
        return f'<User {self.username}>'

    def is_profile_complete(self):
        """检查用户是否完成了个人信息维护"""
        if self.role == 'admin':  # 管理员不需要完善个人信息
            return True
        return all([
            self.gender,
            self.age,
            self.graduation_date,
            self.phone,
            self.school,
            self.college,
            self.profile_completed
        ])

    def is_valid_participant(self):
        """检查用户是否是有效的实验参与者（未毕业或毕业时间在6个月内）"""
        if not self.graduation_date:
            return False
        
        today = datetime.now().date()
        if self.graduation_date > today:  # 未毕业
            return True
            
        # 计算毕业时间是否在6个月内
        delta = today - self.graduation_date
        return delta.days <= 180  # 6个月 = 180天

    @property
    def is_superadmin(self):
        return self.role == 'superadmin'

    @property
    def is_admin(self):
        return self.role == 'admin'

    @property
    def is_participant(self):
        return self.role == 'participant'

    def can_be_modified_by(self, user):
        """检查当前用户是否可以被指定用户修改"""
        if user.is_superadmin:
            return True
        if self.is_superadmin:
            return False
        if user.is_admin and self.is_participant:
            return True
        return False

@login_manager.user_loader
def load_user(id):
    return User.query.get(int(id)) 