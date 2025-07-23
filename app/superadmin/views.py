from flask import render_template, redirect, url_for, flash, request, jsonify, session
from flask_login import login_user, logout_user, login_required, current_user
from . import superadmin
from app import db
from app.models.user import User
from app.models.security import BlockedIP, SecurityLog, LoginAttempt
from app.models.settings import SystemSetting
from functools import wraps
from datetime import datetime, timedelta
import pytz
import os
import shutil
from sqlalchemy import func

def superadmin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_superadmin:
            flash('您没有权限访问此页面。', 'danger')
            return redirect(url_for('superadmin.login'))
        return f(*args, **kwargs)
    return decorated_function

@superadmin.route('/login', methods=['GET', 'POST'])
def login():
    # 如果已经以超级管理员身份登录，直接跳转到仪表盘
    if current_user.is_authenticated and current_user.is_superadmin:
        return redirect(url_for('superadmin.dashboard'))
    # 如果以其他身份登录，先退出登录
    elif current_user.is_authenticated:
        logout_user()
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = request.form.get('remember', False) == 'true'
        
        user = User.query.filter_by(username=username, role='superadmin').first()
        if user is not None and user.verify_password(password):
            # 检查账号状态
            if not user.is_active:
                flash('账号已被禁用，请联系其他超级管理员。', 'error')
                return render_template('superadmin/login.html')
                
            # 设置会话为永久性
            session.permanent = True
            # 登录用户，并设置"记住我"
            login_user(user, remember=remember)
            user.update_last_login()
            
            # 记录登录日志
            login_log = SecurityLog(
                level='info',
                module='auth',
                action='superadmin_login',
                message=f'超级管理员 {user.username} 登录成功',
                user_id=user.id,
                ip_address=request.remote_addr
            )
            db.session.add(login_log)
            db.session.commit()
            
            flash(f'欢迎回来，{user.username}！', 'success')
            return redirect(url_for('superadmin.dashboard'))
            
        # 记录失败的登录尝试
        failed_log = SecurityLog(
            level='warning',
            module='auth',
            action='superadmin_login_failed',
            message=f'超级管理员登录失败，尝试的用户名：{username}',
            ip_address=request.remote_addr
        )
        db.session.add(failed_log)
        db.session.commit()
        
        flash('用户名或密码错误', 'error')
        
    return render_template('superadmin/login.html')

@superadmin.route('/logout')
@login_required
@superadmin_required
def logout():
    logout_user()
    flash('您已退出超级管理员系统', 'info')
    return redirect(url_for('superadmin.login'))

@superadmin.route('/dashboard')
@login_required
@superadmin_required
def dashboard():
    # 获取用户统计数据
    total_users = User.query.count()
    admin_count = User.query.filter_by(role='admin').count()
    participant_count = User.query.filter_by(role='participant').count()
    active_users = User.query.filter_by(is_active=True).count()
    
    return render_template('superadmin/dashboard.html',
                         total_users=total_users,
                         admin_count=admin_count,
                         participant_count=participant_count,
                         active_users=active_users)

@superadmin.route('/users')
@login_required
@superadmin_required
def user_list():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    role = request.args.get('role', '')
    status = request.args.get('status', '')

    query = User.query

    # 搜索条件
    if search:
        query = query.filter(
            db.or_(
                User.username.ilike(f'%{search}%'),
                User.email.ilike(f'%{search}%')
            )
        )

    # 角色筛选
    if role:
        query = query.filter(User.role == role)

    # 状态筛选
    if status:
        is_active = status == 'active'
        query = query.filter(User.is_active == is_active)

    # 排序：超级管理员始终在最前，然后是管理员，最后是普通用户
    query = query.order_by(
        db.case(
            (User.role == 'superadmin', 1),
            (User.role == 'admin', 2),
            else_=3
        ),
        User.created_at.desc()
    )

    users = query.paginate(page=page, per_page=10)
    return render_template('superadmin/user_list.html', users=users)

@superadmin.route('/user/new', methods=['GET', 'POST'])
@login_required
@superadmin_required
def new_user():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role')
        
        if not all([username, email, password, role]):
            flash('请填写所有必填字段', 'error')
            return redirect(url_for('superadmin.new_user'))
            
        if User.query.filter_by(username=username).first():
            flash('用户名已存在', 'error')
            return redirect(url_for('superadmin.new_user'))
            
        if User.query.filter_by(email=email).first():
            flash('邮箱已存在', 'error')
            return redirect(url_for('superadmin.new_user'))
        
        # 检查是否尝试创建超级管理员
        if role == 'superadmin' and User.query.filter_by(role='superadmin').first():
            flash('系统中已存在超级管理员，不能创建第二个超级管理员', 'error')
            return redirect(url_for('superadmin.new_user'))
            
        try:
            user = User(username=username, email=email, role=role)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash(f'用户 {username} 创建成功', 'success')
            return redirect(url_for('superadmin.user_list'))
        except ValueError as e:
            flash(str(e), 'error')
            return redirect(url_for('superadmin.new_user'))
        
    return render_template('superadmin/new_user.html')

@superadmin.route('/user/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@superadmin_required
def edit_user(id):
    user = User.query.get_or_404(id)
    
    if request.method == 'GET':
        return render_template('superadmin/edit_user.html', user=user)
    
    # 不允许修改自己的角色
    if user.id == current_user.id and request.form.get('role') != user.role:
        flash('不能修改自己的角色', 'error')
        return redirect(url_for('superadmin.user_list'))
    
    username = request.form.get('username')
    email = request.form.get('email')
    role = request.form.get('role')
    is_active = request.form.get('is_active') == 'on'
    
    if not all([username, email, role]):
        flash('请填写所有必填字段', 'error')
        return redirect(url_for('superadmin.user_list'))
        
    # 检查用户名唯一性
    existing_user = User.query.filter_by(username=username).first()
    if existing_user and existing_user.id != id:
        flash('用户名已存在', 'error')
        return redirect(url_for('superadmin.user_list'))
        
    # 检查邮箱唯一性
    existing_user = User.query.filter_by(email=email).first()
    if existing_user and existing_user.id != id:
        flash('邮箱已存在', 'error')
        return redirect(url_for('superadmin.user_list'))
    
    # 检查是否尝试将用户升级为超级管理员
    if role == 'superadmin' and user.role != 'superadmin':
        if User.query.filter_by(role='superadmin').first():
            flash('系统中已存在超级管理员，不能创建第二个超级管理员', 'error')
            return redirect(url_for('superadmin.user_list'))
    
    # 不允许降级其他超级管理员
    if user.is_superadmin and role != 'superadmin' and user.id != current_user.id:
        flash('不能降级其他超级管理员的权限', 'error')
        return redirect(url_for('superadmin.user_list'))
    
    # 更新用户信息
    user.username = username
    user.email = email
    user.role = role
    user.is_active = is_active
    
    # 如果提供了新密码则更新密码
    password = request.form.get('password')
    if password:
        user.set_password(password)
    
    try:
        db.session.commit()
        flash(f'用户 {username} 更新成功', 'success')
    except ValueError as e:
        flash(str(e), 'error')
        
    return redirect(url_for('superadmin.user_list'))

@superadmin.route('/user/<int:id>/delete', methods=['POST'])
@login_required
@superadmin_required
def delete_user(id):
    user = User.query.get_or_404(id)
    
    if user.is_superadmin:
        flash('不能删除超级管理员账号', 'error')
        return redirect(url_for('superadmin.user_list'))
        
    db.session.delete(user)
    db.session.commit()
    flash(f'用户 {user.username} 已删除', 'success')
    return redirect(url_for('superadmin.user_list'))

@superadmin.route('/settings')
@login_required
@superadmin_required
def settings():
    return render_template('superadmin/settings.html')

@superadmin.route('/security')
@login_required
@superadmin_required
def security():
    # 获取今天的日期范围
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)
    
    # 获取安全统计数据
    login_attempts = LoginAttempt.query.filter(
        LoginAttempt.timestamp >= today,
        LoginAttempt.timestamp < tomorrow
    ).count()
    
    failed_logins = LoginAttempt.query.filter(
        LoginAttempt.timestamp >= today,
        LoginAttempt.success == False
    ).count()
    
    blocked_ips = BlockedIP.query.count()
    
    # 计算安全评分
    security_score = calculate_security_score()
    
    # 获取安全警告
    security_warnings = get_security_warnings()
    
    # 获取最近活动
    recent_activities = get_recent_activities()
    
    # 获取可疑IP
    suspicious_ips = get_suspicious_ips()
    
    return render_template('superadmin/security.html',
                         login_attempts=login_attempts,
                         failed_logins=failed_logins,
                         blocked_ips=blocked_ips,
                         security_score=security_score,
                         warning_count=len(security_warnings),
                         security_warnings=security_warnings,
                         recent_activities=recent_activities,
                         suspicious_ips=suspicious_ips)

def calculate_security_score():
    score = 100
    
    # 检查是否启用了双因素认证
    settings = SystemSetting.query.first()
    if not settings or not settings.two_factor_auth:
        score -= 15
    
    # 检查过期密码的用户数量
    expired_password_users = User.query.filter(
        User.last_password_change < datetime.now() - timedelta(days=90)
    ).count()
    if expired_password_users > 0:
        score -= min(expired_password_users * 5, 20)
    
    # 检查今日失败的登录尝试
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    failed_attempts = LoginAttempt.query.filter(
        LoginAttempt.timestamp >= today,
        LoginAttempt.success == False
    ).count()
    if failed_attempts > 10:
        score -= min((failed_attempts - 10) * 2, 15)
    
    # 确保分数在0-100之间
    return max(0, min(100, score))

def get_security_warnings():
    warnings = []
    
    # 检查过期密码
    expired_users = User.query.filter(
        User.last_password_change < datetime.now() - timedelta(days=90)
    ).count()
    if expired_users > 0:
        warnings.append({
            'icon': 'bi-shield-exclamation',
            'message': f'存在{expired_users}个用户超过90天未修改密码',
            'action_url': url_for('superadmin.settings')
        })
    
    # 检查双因素认证
    settings = SystemSetting.query.first()
    if not settings or not settings.two_factor_auth:
        warnings.append({
            'icon': 'bi-shield-lock',
            'message': '未启用双因素认证',
            'action_url': url_for('superadmin.settings')
        })
    
    return warnings

def get_recent_activities():
    activities = []
    
    # 获取最近的安全日志
    recent_logs = SecurityLog.query.order_by(
        SecurityLog.timestamp.desc()
    ).limit(10).all()
    
    for log in recent_logs:
        activity = {
            'type': 'warning' if log.level == 'warning' else 'success',
            'icon': 'bi-shield-exclamation' if log.level == 'warning' else 'bi-person-check',
            'title': log.message,
            'time': format_datetime(log.timestamp),
            'status': log.level,
            'status_text': '需要关注' if log.level == 'warning' else '正常'
        }
        if log.details:
            activity['details'] = log.details
        activities.append(activity)
    
    return activities

def get_suspicious_ips():
    suspicious = []
    
    # 获取最近的失败登录尝试
    recent_failures = db.session.query(
        LoginAttempt.ip_address,
        func.count(LoginAttempt.id).label('attempts'),
        func.max(LoginAttempt.timestamp).label('last_attempt')
    ).filter(
        LoginAttempt.success == False,
        LoginAttempt.timestamp >= datetime.now() - timedelta(days=1)
    ).group_by(
        LoginAttempt.ip_address
    ).having(
        func.count(LoginAttempt.id) >= 3
    ).all()
    
    blocked_ips = {ip.ip_address for ip in BlockedIP.query.all()}
    
    for ip, attempts, last_attempt in recent_failures:
        suspicious.append({
            'address': ip,
            'location': get_ip_location(ip),
            'attempts': attempts,
            'last_attempt': format_datetime(last_attempt),
            'is_blocked': ip in blocked_ips
        })
    
    return suspicious

def format_datetime(dt):
    """格式化日期时间为人性化显示"""
    now = datetime.now()
    diff = now - dt
    
    if diff.days == 0:
        if diff.seconds < 60:
            return '刚刚'
        elif diff.seconds < 3600:
            return f'{diff.seconds // 60}分钟前'
        else:
            return f'{diff.seconds // 3600}小时前'
    elif diff.days == 1:
        return '昨天'
    else:
        return dt.strftime('%Y-%m-%d %H:%M')

def get_ip_location(ip):
    """获取IP地址的地理位置（示例实现）"""
    # TODO: 接入真实的IP地理位置服务
    return '未知位置'

@superadmin.route('/logs')
@login_required
@superadmin_required
def logs():
    page = request.args.get('page', 1, type=int)
    level = request.args.get('level')
    module = request.args.get('module')
    date = request.args.get('date')
    
    # 示例日志数据
    logs = [
        {
            'id': 1,
            'level': 'info',
            'module': 'auth',
            'timestamp': '2024-03-15 10:30:00',
            'message': '用户登录成功',
            'details': 'User: admin\nIP: 192.168.1.100\nBrowser: Chrome'
        },
        {
            'id': 2,
            'level': 'warning',
            'module': 'security',
            'timestamp': '2024-03-15 10:25:00',
            'message': '检测到多次登录失败',
            'details': 'IP: 192.168.1.200\nAttempts: 5\nTime Range: 5 minutes'
        },
        {
            'id': 3,
            'level': 'error',
            'module': 'system',
            'timestamp': '2024-03-15 10:20:00',
            'message': '数据库连接失败',
            'details': 'Error: Connection timeout\nDatabase: main\nRetry: 3 times'
        }
    ]
    
    # 模拟分页
    class Pagination:
        def __init__(self, items, page, per_page, total):
            self.items = items
            self.page = page
            self.per_page = per_page
            self.total = total
            self.pages = (total + per_page - 1) // per_page
        
        def iter_pages(self):
            return range(1, self.pages + 1)
    
    paginated_logs = Pagination(logs, page, 10, len(logs))
    
    return render_template('superadmin/logs.html', logs=paginated_logs)

@superadmin.route('/settings/security', methods=['POST'])
@login_required
@superadmin_required
def update_security_settings():
    try:
        two_factor_auth = request.form.get('two_factor_auth') == 'on'
        password_expiry = int(request.form.get('password_expiry', 90))
        login_attempts = int(request.form.get('login_attempts', 5))
        
        # 更新系统设置
        settings = SystemSetting.query.first()
        if not settings:
            settings = SystemSetting()
            db.session.add(settings)
            
        settings.two_factor_auth = two_factor_auth
        settings.password_expiry = password_expiry
        settings.max_login_attempts = login_attempts
        
        db.session.commit()
        flash('安全设置已更新', 'success')
    except Exception as e:
        flash(f'更新安全设置失败：{str(e)}', 'error')
    
    return redirect(url_for('superadmin.settings'))

@superadmin.route('/settings/mail', methods=['POST'])
@login_required
@superadmin_required
def update_mail_settings():
    try:
        smtp_server = request.form.get('smtp_server')
        smtp_port = int(request.form.get('smtp_port', 587))
        sender_email = request.form.get('sender_email')
        
        # 更新邮件设置
        settings = SystemSetting.query.first()
        if not settings:
            settings = SystemSetting()
            db.session.add(settings)
            
        settings.smtp_server = smtp_server
        settings.smtp_port = smtp_port
        settings.sender_email = sender_email
        
        db.session.commit()
        flash('邮件设置已更新', 'success')
    except Exception as e:
        flash(f'更新邮件设置失败：{str(e)}', 'error')
    
    return redirect(url_for('superadmin.settings'))

@superadmin.route('/settings/backup', methods=['POST'])
@login_required
@superadmin_required
def backup_database():
    try:
        # 这里实现数据库备份逻辑
        # 示例：创建一个简单的SQLite备份
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = f'backups/backup_{timestamp}.db'
        
        # 确保备份目录存在
        os.makedirs('backups', exist_ok=True)
        
        # 复制数据库文件
        shutil.copy2('app.db', backup_path)
        
        return jsonify({'success': True, 'message': '数据库备份成功'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@superadmin.route('/settings/cleanup', methods=['POST'])
@login_required
@superadmin_required
def cleanup_temp_files():
    try:
        # 这里实现临时文件清理逻辑
        # 示例：清理上传目录中的临时文件
        temp_dir = 'app/static/uploads/temp'
        if os.path.exists(temp_dir):
            now = datetime.now()
            for filename in os.listdir(temp_dir):
                filepath = os.path.join(temp_dir, filename)
                file_modified = datetime.fromtimestamp(os.path.getmtime(filepath))
                if now - file_modified > timedelta(days=1):  # 删除超过1天的临时文件
                    os.remove(filepath)
        
        return jsonify({'success': True, 'message': '临时文件清理成功'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@superadmin.route('/block_ip', methods=['POST'])
@login_required
@superadmin_required
def block_ip():
    try:
        ip = request.json.get('ip')
        if not ip:
            raise ValueError('IP地址不能为空')
            
        # 检查IP是否已经被封禁
        blocked_ip = BlockedIP.query.filter_by(ip_address=ip).first()
        if blocked_ip:
            return jsonify({'success': False, 'message': 'IP已经被封禁'})
            
        # 创建新的封禁记录
        blocked_ip = BlockedIP(
            ip_address=ip,
            blocked_by=current_user.id,
            blocked_at=datetime.now(),
            reason='可疑活动'
        )
        db.session.add(blocked_ip)
        db.session.commit()
        
        # 记录操作日志
        log = SecurityLog(
            level='warning',
            module='security',
            action='block_ip',
            user_id=current_user.id,
            ip_address=ip,
            message=f'封禁IP: {ip}'
        )
        db.session.add(log)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'IP已成功封禁'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@superadmin.route('/unblock_ip', methods=['POST'])
@login_required
@superadmin_required
def unblock_ip():
    try:
        ip = request.json.get('ip')
        if not ip:
            raise ValueError('IP地址不能为空')
            
        # 查找并删除封禁记录
        blocked_ip = BlockedIP.query.filter_by(ip_address=ip).first()
        if not blocked_ip:
            return jsonify({'success': False, 'message': 'IP未被封禁'})
            
        db.session.delete(blocked_ip)
        
        # 记录操作日志
        log = SecurityLog(
            level='info',
            module='security',
            action='unblock_ip',
            user_id=current_user.id,
            ip_address=ip,
            message=f'解除IP封禁: {ip}'
        )
        db.session.add(log)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'IP封禁已解除'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@superadmin.route('/export_logs')
@login_required
@superadmin_required
def export_logs():
    # TODO: 实现日志导出逻辑
    return "导出日志功能待实现" 