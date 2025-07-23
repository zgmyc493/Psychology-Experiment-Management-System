from flask import Flask, redirect, url_for, flash, request
from config import Config
from .extensions import init_extensions, db, csrf
from flask_login import current_user, logout_user
from .models.system_setting import SystemSetting
from app.models.notification import Notification
from app.utils import task_scheduler

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # 初始化所有扩展
    init_extensions(app)

    # 检查数据库是否已初始化
    with app.app_context():
        db.create_all()  # 创建所有表
        setting = SystemSetting.query.filter_by(key='db_initialized').first()
        if not setting:
            # 首次运行，初始化数据库
            setting = SystemSetting(
                key='db_initialized',
                value='true',
                description='标记数据库是否已经初始化'
            )
            db.session.add(setting)
            db.session.commit()
            print('数据库首次初始化完成')

    # 注册蓝图
    from .main import main as main_blueprint
    app.register_blueprint(main_blueprint)

    from .auth import auth as auth_blueprint
    app.register_blueprint(auth_blueprint, url_prefix='/auth')

    from .admin import admin as admin_blueprint
    app.register_blueprint(admin_blueprint, url_prefix='/admin')

    from .superadmin import superadmin as superadmin_blueprint
    app.register_blueprint(superadmin_blueprint, url_prefix='/superadmin')

    # 启动自动任务调度器
    task_scheduler.init_app(app)

    @app.before_request
    def check_user_role():
        # 忽略静态文件请求
        if request.path.startswith('/static'):
            return
            
        # 定义公共路由
        public_routes = [
            '/auth/login',
            '/auth/register',
            '/auth/reset_password_request',
            '/auth/captcha'
        ]
        
        # 处理根路径
        if request.path == '/':
            if not current_user.is_authenticated:
                return  # 未登录用户可以访问首页
            # 已登录用户根据角色重定向
            if current_user.is_superadmin:
                return redirect(url_for('superadmin.dashboard'))
            elif current_user.is_admin:
                return redirect(url_for('admin.index'))
            else:
                return redirect(url_for('main.user_home'))  # 普通用户直接进入用户首页
        
        # 处理登出路由
        if request.path.startswith('/auth/logout'):
            if current_user.is_authenticated:
                if current_user.is_superadmin:
                    logout_user()
                    flash('您已退出超级管理员系统', 'info')
                    return redirect(url_for('superadmin.login'))
                elif current_user.is_admin:
                    logout_user()
                    flash('您已退出管理员系统', 'info')
                    return redirect(url_for('auth.login'))
            return
            
        # 检查是否已登录的超级管理员
        if current_user.is_authenticated and current_user.is_superadmin:
            # 允许访问超级管理员登录页面和登出路由
            if request.path == '/superadmin/login' or request.path.startswith('/auth/logout'):
                return
            # 如果不是访问超级管理员页面，重定向到超级管理员仪表盘
            if not request.path.startswith('/superadmin'):
                return redirect(url_for('superadmin.dashboard'))
            return
            
        # 检查是否已登录的管理员
        if current_user.is_authenticated and current_user.is_admin:
            # 允许访问管理员路由
            if request.path.startswith('/admin'):
                return
            # 如果访问超级管理员页面，拒绝访问
            if request.path.startswith('/superadmin'):
                flash('您没有权限访问超级管理员页面', 'warning')
                return redirect(url_for('admin.index'))
            return
            
        # 处理公共路由
        if request.path in public_routes:
            return
            
        # 处理超级管理员路由
        if request.path.startswith('/superadmin'):
            if request.path == '/superadmin/login':  # 允许访问超级管理员登录页面
                return
            if not current_user.is_authenticated:
                return redirect(url_for('superadmin.login'))
            elif not current_user.is_superadmin:
                flash('您没有权限访问超级管理员页面', 'warning')
                return redirect(url_for('main.index'))
            return
            
        # 处理管理员路由
        if request.path.startswith('/admin'):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))
            elif not (current_user.is_admin or current_user.is_superadmin):
                flash('您没有权限访问管理员页面', 'warning')
                return redirect(url_for('main.index'))
            return
            
        # 处理普通用户路由
        if current_user.is_authenticated:
            if current_user.role == 'participant' and not current_user.is_profile_complete():
                # 允许访问个人信息页面和登出
                if not (request.path == '/main/profile' or request.path.startswith('/auth/logout')):
                    flash('请先完善您的个人信息', 'warning')
                    return redirect(url_for('main.profile'))
        else:
            # 未登录用户只能访问公共路由和首页
            if request.path not in public_routes and request.path != '/':
                return redirect(url_for('auth.login'))

    return app

from app import models 