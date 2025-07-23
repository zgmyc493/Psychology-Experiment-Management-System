from flask_mail import Mail
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect

# 初始化扩展实例
db = SQLAlchemy()
migrate = Migrate()
mail = Mail()
login_manager = LoginManager()
csrf = CSRFProtect()

def init_extensions(app):
    """初始化所有扩展"""
    # 配置登录管理器
    login_manager.login_view = 'auth.login'
    login_manager.login_message = '请先登录'
    login_manager.login_message_category = 'info'
    
    # 初始化扩展
    db.init_app(app)
    migrate.init_app(app, db)
    mail.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app) 