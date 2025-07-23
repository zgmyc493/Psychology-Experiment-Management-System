from flask import render_template, redirect, url_for, flash, request, jsonify, send_file, current_app
from flask_login import login_required, current_user
from . import main
from .forms import ExperimentForm, ProfileForm
from app.models.user import User
from app.models.experiment import Experiment, Participation, ExperimentInvitation, ExperimentReservation
from app import db
from datetime import datetime, date, timedelta
import csv
import io
from functools import wraps
import os
import json
import pandas as pd
from io import BytesIO
from app.models.notification import Notification
import random
import string

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('您没有权限访问此页面。', 'danger')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function

def profile_required(f):
    """检查用户是否完成个人信息维护的装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if current_user.role != 'admin' and not current_user.is_profile_complete():
            flash('请先完善您的个人信息', 'warning')
            return redirect(url_for('main.profile'))
        return f(*args, **kwargs)
    return decorated_function

@main.route('/')
def index():
    """首页"""
    # 检查并自动开启已到开启时间的实验
    check_auto_start_experiments()
    
    if current_user.is_authenticated:
        if current_user.is_superadmin:
            return redirect(url_for('superadmin.dashboard'))
        elif current_user.role == 'admin':
            return redirect(url_for('admin.index'))
        else:
            return redirect(url_for('main.user_home'))
            
    return render_template('main/index.html')

@main.route('/home')
@login_required
@profile_required
def user_home():
    """已登录普通用户的首页"""
    # 检查并自动开启已到开启时间的实验
    check_auto_start_experiments()
    
    if current_user.role == 'admin':
        return redirect(url_for('admin.index'))
    
    # 获取用户统计数据
    participations = current_user.participations
    total = participations.count()
    completed = participations.filter_by(status='completed').count()
    
    # 获取最近参与的5个实验
    recent_participations = Participation.query.filter_by(
        user_id=current_user.id
    ).order_by(Participation.updated_at.desc()).limit(5).all()
    
    # 参与状态映射
    status_map = {
        'pending': '待开始',
        'started': '进行中',
        'completed': '已完成',
        'cancelled': '已取消'
    }
    
    # 获取用户参与的实验ID列表
    participated_experiment_ids = [p.experiment_id for p in participations]
    
    # 获取可参与的实验（公开的、未参与的、未删除的、处于活跃状态的）
    available_experiments = Experiment.query.filter(
        Experiment.status == 'active',  # 活跃状态
        Experiment.deleted_at == None,  # 未删除
        ~Experiment.id.in_(participated_experiment_ids),  # 未参与
        Experiment.visibility == 'public'  # 仅公开实验
    ).all()
    
    # 获取用户收到的邀请
    invitations = ExperimentInvitation.query.filter_by(
        user_id=current_user.id,
        status='pending'
    ).all()
    
    # 获取邀请的实验
    invitations_pending = ExperimentInvitation.query.filter_by(
        user_id=current_user.id,
        status='pending'
    ).order_by(ExperimentInvitation.invited_at.desc()).limit(3).all()
    
    # 获取用户的预约数量
    reservations_count = ExperimentReservation.query.filter_by(
        user_id=current_user.id,
        status='pending'
    ).count()
    
    # 创建用户统计字典
    user_stats = {
        'total_experiments': total,
        'completed_experiments': completed,
        'points': calculate_user_points(current_user),
        'completion_rate': str(round(completed / total * 100)) if total > 0 else '0'
    }
    
    return render_template('main/user_home.html',
                         total_experiments=total,
                         completed_experiments=completed,
                         recent_participations=recent_participations,
                         available_experiments=available_experiments,
                         invitations=invitations_pending,
                         user_stats=user_stats,
                         status_map=status_map,
                         points=calculate_user_points(current_user),
                         reservations_count=reservations_count)

@main.route('/experiment')
@login_required
@profile_required
def experiment():
    """实验管理首页"""
    # 检查并自动开启已到开启时间的实验
    check_auto_start_experiments()
    
    # 如果是管理员，显示所有实验
    if current_user.role == 'admin':
        # 获取所有未删除的实验
        experiments = Experiment.query.filter(
            Experiment.deleted_at == None
        ).order_by(Experiment.created_at.desc()).all()
        
        return render_template('main/experiment.html', experiments=experiments, is_admin=True, timedelta=timedelta)
    
    # 如果是普通用户，显示自己创建的实验
    experiments = Experiment.query.filter_by(
        creator_id=current_user.id,
        deleted_at=None
    ).order_by(Experiment.created_at.desc()).all()
    
    # 获取用户参与的实验
    participations = Participation.query.filter_by(
        user_id=current_user.id
    ).all()
    
    # 获取用户可参与的实验
    participated_experiment_ids = [p.experiment_id for p in participations]
    available_experiments = Experiment.query.filter(
        Experiment.status == 'active',
        Experiment.deleted_at == None,
        ~Experiment.id.in_(participated_experiment_ids),
        Experiment.visibility == 'public'
    ).all()
    
    # 检查用户是否有未读通知
    unread_count = Notification.query.filter_by(
        user_id=current_user.id,
        read=False
    ).count()
    
    return render_template('main/experiment.html',
                         experiments=experiments,
                         participations=participations,
                         available_experiments=available_experiments,
                         is_admin=False,
                         unread_count=unread_count,
                         timedelta=timedelta)

def check_auto_start_experiments():
    """检查并自动开启已到开启时间的实验"""
    try:
        # 获取当前UTC时间
        current_time = datetime.utcnow()
        print(f"[视图函数] 当前UTC时间: {current_time}")
        print(f"[视图函数] 当前北京时间: {current_time + timedelta(hours=8)}")
        
        # 查找所有需要自动开启的实验（注意：数据库中已经存储的是UTC时间）
        experiments_to_check = Experiment.query.filter(
            Experiment.status == 'draft',
            Experiment.scheduled_start_time != None,
            Experiment.scheduled_start_time <= current_time  # 确保只查找已过计划时间的实验
        ).all()
        
        if experiments_to_check:
            print(f"[视图函数] 找到 {len(experiments_to_check)} 个应该开始的草稿实验")
            
            # 开启所有满足条件的实验
            for exp in experiments_to_check:
                try:
                    # 显示时间信息
                    beijing_time = exp.scheduled_start_time + timedelta(hours=8) if exp.scheduled_start_time else "未设置"
                    print(f"[视图函数] 实验ID={exp.id}, 标题={exp.title}")
                    print(f"[视图函数] 计划时间(UTC): {exp.scheduled_start_time}")
                    print(f"[视图函数] 计划时间(北京): {beijing_time}")
                    
                    exp.status = 'active'
                    print(f"[视图函数] 实验状态已更改为: active")
                    
                    # 创建通知给管理员
                    notification = Notification(
                        user_id=exp.creator_id,
                        title='实验自动开启',
                        message=f'您的实验 "{exp.title}" 已按计划自动开启招募。',
                        type='experiment_auto_started'
                    )
                    db.session.add(notification)
                    
                    # 先提交状态变更，以便后续处理
                    db.session.commit()
                    
                    # 处理所有预约
                    pending_reservations = ExperimentReservation.query.filter_by(
                        experiment_id=exp.id,
                        status='pending'
                    ).all()
                    
                    if pending_reservations:
                        print(f"[视图函数] 找到 {len(pending_reservations)} 个待处理的预约")
                        
                        # 将预约用户自动加入实验
                        for reservation in pending_reservations:
                            try:
                                # 检查是否已经有参与记录
                                existing_participation = Participation.query.filter_by(
                                    experiment_id=exp.id,
                                    user_id=reservation.user_id
                                ).first()
                                
                                if not existing_participation:
                                    participation = reservation.auto_join()
                                    
                                    # 创建通知告知用户已自动加入
                                    notification = Notification(
                                        user_id=reservation.user_id,
                                        title='已自动加入实验',
                                        message=f'您预约的实验"{exp.title}"已开始招募，系统已自动为您加入该实验。',
                                        type='auto_joined_experiment'
                                    )
                                    db.session.add(notification)
                                    
                                    # 提交每个用户的加入操作
                                    db.session.commit()
                                    print(f"[视图函数] 用户ID={reservation.user_id} 已自动加入实验")
                            except Exception as e:
                                db.session.rollback()
                                print(f"[视图函数] 处理用户 {reservation.user_id} 预约时出错: {str(e)}")
                                import traceback
                                print(traceback.format_exc())
                except Exception as e:
                    db.session.rollback()
                    print(f"[视图函数] 处理实验 {exp.id} 时出错: {str(e)}")
                    import traceback
                    print(traceback.format_exc())
            
            print(f"[视图函数] 成功处理了 {len(experiments_to_check)} 个实验")
        else:
            # 查找所有设置了计划时间但尚未到时间的草稿实验
            future_experiments = Experiment.query.filter(
                Experiment.status == 'draft',
                Experiment.scheduled_start_time != None,
                Experiment.scheduled_start_time > current_time
            ).all()
            
            if future_experiments:
                print(f"[视图函数] 找到 {len(future_experiments)} 个尚未到开始时间的草稿实验")
                # 显示最近计划启动的实验
                for exp in future_experiments:
                    remaining = exp.scheduled_start_time - current_time
                    beijing_time = exp.scheduled_start_time + timedelta(hours=8)
                    print(f"[视图函数] 实验ID={exp.id}, 标题={exp.title}")
                    print(f"[视图函数] 计划时间(UTC): {exp.scheduled_start_time}")
                    print(f"[视图函数] 计划时间(北京): {beijing_time}")
                    print(f"[视图函数] 距离开始还有: {remaining}")
    except Exception as e:
        print(f"[视图函数] 自动开启实验时出错: {str(e)}")
        import traceback
        print(traceback.format_exc())
        db.session.rollback()

@main.route('/experiment/new', methods=['GET', 'POST'])
@login_required
def new_experiment():
    form = ExperimentForm()
    if form.validate_on_submit():
        try:
            # 创建实验记录
            experiment = Experiment(
                title=form.title.data,
                description=form.description.data,
                duration=form.duration.data,
                reward=form.reward.data,
                visibility='private',  # 使用默认设置，后续在编辑页面进行更改
                creator_id=current_user.id,
                status='draft'
            )
            
            # 生成邀请码
            experiment.invite_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            
            db.session.add(experiment)
            db.session.commit()
            flash('实验创建成功！', 'success')
            if current_user.role == 'admin':
                return redirect(url_for('admin.experiment_list'))
            return redirect(url_for('main.experiment_detail', id=experiment.id))
        except Exception as e:
            db.session.rollback()
            flash(f'创建实验失败: {str(e)}', 'danger')
            print(f"创建实验时出错: {str(e)}")
    elif request.method == 'POST':
        # 如果表单验证失败，显示错误信息
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"{getattr(form, field).label.text}: {error}", 'danger')
                
    # 无论是GET请求还是表单验证失败的POST请求，都显示表单
    return render_template('main/new_experiment.html', form=form)

@main.route('/experiment/<int:id>')
@login_required
@profile_required
def experiment_detail(id):
    """实验详情"""
    # 检查并自动开启已到开启时间的实验
    check_auto_start_experiments()
    
    experiment = Experiment.query.get_or_404(id)
    
    if experiment.deleted_at is not None and not current_user.is_admin:
        flash('实验不存在或已被删除', 'warning')
        return redirect(url_for('main.experiment'))
    
    # 获取当前用户的参与记录
    participation = None
    if current_user.is_authenticated:
        participation = Participation.query.filter_by(
            user_id=current_user.id,
            experiment_id=id
        ).first()
    
    # 获取实验邀请记录
    invitation = None
    if current_user.is_authenticated:
        invitation = ExperimentInvitation.query.filter_by(
            user_id=current_user.id,
            experiment_id=id
        ).first()
    
    # 获取当前时间
    now = datetime.utcnow()
    
    return render_template('main/experiment_detail.html',
                         experiment=experiment,
                         participation=participation,
                         invitation=invitation,
                         now=now,
                         timedelta=timedelta)

@main.route('/experiment/<int:id>/join')
@login_required
@profile_required
def join_experiment(id):
    if current_user.role == 'admin':
        flash('管理员不能参与实验', 'error')
        return redirect(url_for('main.experiment'))
    
    experiment = Experiment.query.get_or_404(id)
    if experiment.status != 'active':
        flash('该实验当前不接受报名', 'error')
        return redirect(url_for('main.experiment'))
    
    # 检查是否是公开实验或已接受邀请
    if experiment.visibility != 'public':
        invitation = ExperimentInvitation.query.filter_by(
            experiment_id=id,
            user_id=current_user.id,
            status='accepted'
        ).first()
        if not invitation:
            flash('您需要先接受实验邀请才能参加此实验。', 'warning')
            return redirect(url_for('main.experiment'))
    
    # 检查是否满足参与要求
    if experiment.min_age and current_user.age < experiment.min_age:
        flash(f'您不满足实验的年龄要求（最小年龄：{experiment.min_age}岁）', 'error')
        return redirect(url_for('main.experiment_detail', id=id))
        
    if experiment.max_age and current_user.age > experiment.max_age:
        flash(f'您不满足实验的年龄要求（最大年龄：{experiment.max_age}岁）', 'error')
        return redirect(url_for('main.experiment_detail', id=id))
        
    if experiment.required_gender and experiment.required_gender != 'any' and current_user.gender != experiment.required_gender:
        gender_map = {'male': '男性', 'female': '女性', 'any': '不限'}
        flash(f'您不满足实验的性别要求（要求性别：{gender_map.get(experiment.required_gender, "不限")}）', 'error')
        return redirect(url_for('main.experiment_detail', id=id))
    
    # 检查是否已参与
    participation = Participation.query.filter_by(
        experiment_id=id,
        user_id=current_user.id
    ).first()
    
    if participation:
        flash('您已经参与了该实验。', 'warning')
        return redirect(url_for('main.experiment_detail', id=id))
    
    # 创建参与记录
    participation = Participation(
        experiment_id=id,
        user_id=current_user.id,
        status='pending'
    )
    
    db.session.add(participation)
    db.session.commit()
    
    flash('成功加入实验！', 'success')
    return redirect(url_for('main.experiment_detail', id=id))

@main.route('/edit_experiment/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_experiment(id):
    """编辑实验"""
    experiment = Experiment.query.get_or_404(id)
    
    # 检查是否有权限编辑
    if not current_user.is_admin and current_user.id != experiment.creator_id:
        flash('您没有权限编辑此实验', 'warning')
        return redirect(url_for('main.experiment'))
    
    form = ExperimentForm()
    
    if form.validate_on_submit():
        experiment.title = form.title.data
        experiment.description = form.description.data
        experiment.duration = form.duration.data
        experiment.reward = form.reward.data
        experiment.visibility = form.visibility.data
        experiment.categories = form.categories.data or []
        experiment.min_age = form.min_age.data
        experiment.max_age = form.max_age.data
        experiment.required_gender = form.required_gender.data
        experiment.requirements = form.requirements.data
        experiment.max_participants = form.max_participants.data
        experiment.auto_close = form.auto_close.data
        experiment.external_url = form.external_url.data
        experiment.auto_approve = form.auto_approve.data
        experiment.send_reminder = form.send_reminder.data
        experiment.allow_withdrawal = form.allow_withdrawal.data
        experiment.notes = form.notes.data
        
        # 处理计划开始时间（将北京时间转换为UTC时间）
        try:
            if form.scheduled_start_time.data:
                # 假设用户输入的是北京时间，需要转换为UTC时间
                beijing_time = form.scheduled_start_time.data
                # 北京时间比UTC早8小时，所以UTC时间 = 北京时间 - 8小时
                utc_time = beijing_time - timedelta(hours=8)
                experiment.scheduled_start_time = utc_time
                print(f"保存计划开始时间 - 北京时间: {beijing_time}, UTC时间: {utc_time}")
            else:
                experiment.scheduled_start_time = None
                print("未设置计划开始时间")
        except Exception as e:
            flash(f'日期时间格式有误，请使用正确的格式（YYYY-MM-DD HH:MM）: {str(e)}', 'error')
            print(f"时间转换错误: {str(e)}")
        
        if not experiment.invite_code:
            # 生成8位随机字母数字邀请码
            experiment.invite_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            
        db.session.commit()
        flash('实验更新成功', 'success')
        return redirect(url_for('main.experiment_detail', id=experiment.id))
    
    elif request.method == 'GET':
        form.title.data = experiment.title
        form.description.data = experiment.description
        form.duration.data = experiment.duration
        form.reward.data = experiment.reward
        form.visibility.data = experiment.visibility
        form.categories.data = experiment.categories
        form.min_age.data = experiment.min_age
        form.max_age.data = experiment.max_age
        form.required_gender.data = experiment.required_gender
        form.requirements.data = experiment.requirements
        form.max_participants.data = experiment.max_participants
        form.auto_close.data = experiment.auto_close
        form.external_url.data = experiment.external_url
        form.auto_approve.data = experiment.auto_approve
        form.send_reminder.data = experiment.send_reminder
        form.allow_withdrawal.data = experiment.allow_withdrawal
        form.notes.data = experiment.notes
        
        # 如果有计划开始时间，将UTC时间转换为北京时间显示
        if experiment.scheduled_start_time:
            # UTC时间 + 8小时 = 北京时间
            beijing_time = experiment.scheduled_start_time + timedelta(hours=8)
            form.scheduled_start_time.data = beijing_time
            print(f"显示计划开始时间 - UTC时间: {experiment.scheduled_start_time}, 北京时间: {beijing_time}")
    
    # 获取当前时间，用于最小日期限制
    now = datetime.utcnow()
    
    return render_template('main/edit_experiment.html', form=form, experiment=experiment, now=now, timedelta=timedelta)

@main.route('/experiment/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_experiment(id):
    experiment = Experiment.query.get_or_404(id)
    
    # 获取所有参与者
    participants = [p.user for p in experiment.participations.all()]
    
    experiment.soft_delete(current_user.id)
    
    # 为每个参与者创建通知
    for participant in participants:
        notification = Notification(
            user_id=participant.id,
            title='实验已删除',
            message=f'您参与的实验"{experiment.title}"已被管理员删除并移至回收站。',
            type='experiment_deleted'
        )
        db.session.add(notification)
    
        db.session.commit()
    flash(f'实验"{experiment.title}"已移至回收站', 'info')
    return redirect(url_for('main.experiment'))

@main.route('/experiment/<int:id>/toggle_status', methods=['GET', 'POST'])
@login_required
@admin_required
def toggle_experiment_status(id):
    """切换实验状态（开始/结束招募）"""
    experiment = Experiment.query.get_or_404(id)
    
    if experiment.status == 'draft':
        experiment.status = 'active'
        
        # 提交状态变化，以便后续查询能看到最新状态
        db.session.commit()
        
        # 查找所有待处理的预约
        pending_reservations = ExperimentReservation.query.filter_by(
            experiment_id=experiment.id,
            status='pending'
        ).all()
        
        # 将预约用户自动加入实验
        joined_users = []
        for reservation in pending_reservations:
            try:
                # 检查是否已经有参与记录
                existing_participation = Participation.query.filter_by(
                    experiment_id=experiment.id,
                    user_id=reservation.user_id
                ).first()
                
                if not existing_participation:
                    participation = reservation.auto_join()
                    
                    # 创建通知告知用户已自动加入
                    notification = Notification(
                        user_id=reservation.user_id,
                        title='已自动加入实验',
                        message=f'您预约的实验"{experiment.title}"已开始招募，系统已自动为您加入该实验。',
                        type='auto_joined_experiment'
                    )
                    db.session.add(notification)
                    joined_users.append(reservation.user_id)
                    
                    # 提交每个用户的加入操作，避免一个错误影响所有用户
                    db.session.commit()
                    print(f"[实验状态变更] 用户 {reservation.user_id} 已自动加入实验 {experiment.id}")
            except Exception as e:
                db.session.rollback()
                print(f"[实验状态变更] 自动加入用户 {reservation.user_id} 失败: {str(e)}")
                import traceback
                print(traceback.format_exc())
        
        if joined_users:
            flash(f'实验已开始招募，并自动添加了{len(joined_users)}名预约用户', 'success')
        else:
            flash('实验已开始招募', 'success')
    
    elif experiment.status == 'active':
        experiment.status = 'completed'
        flash('实验招募已结束', 'info')
        db.session.commit()
    
    return redirect(url_for('main.experiment_detail', id=id))

@main.route('/experiment/<int:id>/export')
@login_required
@admin_required
def export_experiment_data(id):
    experiment = Experiment.query.get_or_404(id)
    participations = Participation.query.filter_by(experiment_id=id).all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # 写入表头
    writer.writerow(['参与者ID', '用户名', '状态', '开始时间', '完成时间'])
    
    # 写入数据
    for p in participations:
        writer.writerow([
            p.user_id,
            p.user.username,
            p.status,
            p.started_at.strftime('%Y-%m-%d %H:%M:%S') if p.started_at else '',
            p.completed_at.strftime('%Y-%m-%d %H:%M:%S') if p.completed_at else ''
        ])
    
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8-sig')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'experiment_{id}_data.csv'
    )

@main.route('/experiment/<int:id>/start')
@login_required
def start_experiment(id):
    participation = Participation.query.filter_by(
        user_id=current_user.id,
        experiment_id=id
    ).first_or_404()
    
    if participation.status != 'pending':
        flash('实验状态无法更改', 'error')
    else:
        participation.status = 'started'
        participation.started_at = datetime.utcnow()
        db.session.commit()
        flash('实验已开始', 'success')
    
    return redirect(url_for('main.experiment_detail', id=id))

@main.route('/experiment/<int:id>/complete')
@login_required
def complete_experiment(id):
    participation = Participation.query.filter_by(
        user_id=current_user.id,
        experiment_id=id
    ).first_or_404()
    
    if participation.status != 'started':
        flash('实验状态无法更改', 'error')
    else:
        participation.status = 'completed'
        participation.completed_at = datetime.utcnow()
        db.session.commit()
        flash('实验已完成', 'success')
    
    return redirect(url_for('main.experiment_detail', id=id))

def calculate_completion_rate():
    total = Participation.query.count()
    if total == 0:
        return '0'
    completed = Participation.query.filter_by(status='completed').count()
    return str(round(completed / total * 100))

def calculate_user_points(user):
    # 直接通过 participations 关系获取已完成的实验数量
    completed_count = user.participations.filter_by(status='completed').count()
    return completed_count * 10  # 每完成一个实验获得10积分

@main.route('/available_experiments')
@login_required
def available_experiments():
    """可参与的实验列表"""
    # 管理员不能参与实验
    if current_user.role == 'admin':
        flash('管理员不能参与实验', 'warning')
        return redirect(url_for('main.experiment'))
        
    # 检查并自动开启已到开启时间的实验
    check_auto_start_experiments()
    
    # 获取用户已参与的实验ID列表
    participations = Participation.query.filter_by(user_id=current_user.id).all()
    participation_experiment_ids = [p.experiment_id for p in participations]
    
    # 获取可参与的实验（公开的、未参与的、未删除的、处于活跃状态的）
    experiments = Experiment.query.filter(
        Experiment.status == 'active',  # 活跃状态
        Experiment.deleted_at == None,  # 未删除
        ~Experiment.id.in_(participation_experiment_ids),  # 未参与
        Experiment.visibility == 'public'  # 仅公开实验
    ).all()
    
    # 调试输出，查看查询到的实验的可见性
    print("查询到的实验:")
    for e in experiments:
        print(f"实验ID: {e.id}, 标题: {e.title}, 可见性: {e.visibility}")
    
    # 再次筛选，严格确保只有公开实验
    experiments = [e for e in experiments if e.visibility == 'public']
    
    return render_template('main/available_experiments.html', experiments=experiments, timedelta=timedelta)

@main.route('/experiment/create', methods=['GET', 'POST'])
@login_required
def create_experiment():
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        duration = request.form.get('duration')
        reward = request.form.get('reward')
        invited_users = request.form.getlist('invited_users')  # 获取被邀请的用户ID列表
        
        experiment = Experiment(
            title=title,
            description=description,
            duration=duration,
            reward=reward,
            creator_id=current_user.id,
            status='draft'
        )
        db.session.add(experiment)
        db.session.flush()  # 获取experiment.id
        
        # 创建邀请记录
        for user_id in invited_users:
            invitation = ExperimentInvitation(
                user_id=user_id,
                experiment_id=experiment.id
            )
            db.session.add(invitation)
        
        db.session.commit()
        flash('实验创建成功！邀请码：' + experiment.invite_code, 'success')
        if current_user.role == 'admin':
            return redirect(url_for('admin.experiment_list'))
        return redirect(url_for('main.experiment_detail', id=experiment.id))
    
    # GET请求，显示创建表单
    users = User.query.filter(User.id != current_user.id).all()
    return render_template('main/create_experiment.html', users=users)

@main.route('/experiment/<int:id>/invite', methods=['POST'])
@login_required
def invite_to_experiment(id):
    """邀请用户参加实验"""
    if current_user.role != 'admin':
        flash('只有管理员可以邀请用户。', 'error')
        return redirect(url_for('main.experiment_detail', id=id))
    
    experiment = Experiment.query.get_or_404(id)
    user_ids = request.form.getlist('user_ids')
    
    if not user_ids:
        flash('请选择至少一名用户进行邀请。', 'warning')
        return redirect(url_for('main.experiment_detail', id=id))
    
    # 统计数据
    invited_count = 0
    skipped_count = 0
    
    for user_id in user_ids:
        try:
            user_id = int(user_id)
            # 检查是否为超级管理员
            user = User.query.get(user_id)
            if not user:
                skipped_count += 1
                continue
                
            if user.role == 'superadmin':
                skipped_count += 1
                continue  # 跳过超级管理员
                
            # 检查是否已经邀请过
            existing_invitation = ExperimentInvitation.query.filter_by(
                experiment_id=id, user_id=user_id, status='pending'
            ).first()
            
            if existing_invitation:
                skipped_count += 1
                continue  # 已邀请过，跳过
            
            # 检查年龄和性别要求
            if experiment.min_age and (not user.age or user.age < experiment.min_age):
                skipped_count += 1
                continue  # 不符合最小年龄要求
                
            if experiment.max_age and (not user.age or user.age > experiment.max_age):
                skipped_count += 1
                continue  # 不符合最大年龄要求
                
            if experiment.required_gender != 'any' and experiment.required_gender and user.gender != experiment.required_gender:
                skipped_count += 1
                continue  # 不符合性别要求
            
            # 创建新邀请
            invitation = ExperimentInvitation(
                experiment_id=id,
                user_id=user_id,
                created_by_id=current_user.id
            )
            db.session.add(invitation)
            db.session.flush()  # 获取邀请ID
            
            # 创建通知，在消息中包含必要的信息
            notification_message = f'您收到了实验"{experiment.title}"的邀请，请及时查看并回应。邀请ID:{invitation.id}'
            notification = Notification(
                user_id=user_id,
                title='新的实验邀请',
                message=notification_message,
                type='experiment_invitation'
            )
            db.session.add(notification)
            invited_count += 1
        except Exception as e:
            app.logger.error(f"Error inviting user {user_id}: {str(e)}")
            skipped_count += 1
    
    db.session.commit()
    
    # 显示邀请结果
    if invited_count > 0:
        if skipped_count > 0:
            flash(f'成功邀请了 {invited_count} 名用户。{skipped_count} 名用户被跳过（已邀请过或不符合条件）。', 'info')
        else:
            flash(f'成功邀请了 {invited_count} 名用户。', 'success')
    else:
        flash('没有发送邀请。所选用户可能已经被邀请过或不符合实验条件。', 'warning')
    
    return redirect(url_for('main.experiment_detail', id=id))

@main.route('/experiment/join/<invite_code>', methods=['GET', 'POST'])
@login_required
def join_experiment_by_code(invite_code):
    """通过URL中的邀请码加入实验"""
    # 管理员不能参与实验
    if current_user.role == 'admin':
        flash('管理员不能参与实验', 'error')
        return redirect(url_for('main.experiment'))
        
    experiment = Experiment.query.filter_by(invite_code=invite_code).first()
    if not experiment:
        flash('无效的邀请码。', 'danger')
        return redirect(url_for('main.index'))
    
    # 检查实验状态
    if experiment.status != 'active':
        flash('该实验尚未开始招募，请等待管理员开启实验。', 'warning')
        return redirect(url_for('main.index'))
    
    # 检查是否为公开实验，如果是公开实验不需要邀请码
    if experiment.visibility == 'public':
        flash('这是一个公开实验，无需邀请码即可参与。', 'info')
        return redirect(url_for('main.experiment_detail', id=experiment.id))
    
    # 检查是否已经参与
    existing_participation = Participation.query.filter_by(
        experiment_id=experiment.id, 
        user_id=current_user.id
    ).first()
    
    if existing_participation:
        flash('您已经参与了这个实验。', 'info')
        return redirect(url_for('main.experiment_detail', id=experiment.id))
    
    # 检查是否满足参与要求
    if experiment.min_age and current_user.age < experiment.min_age:
        flash(f'您不满足实验的年龄要求（最小年龄：{experiment.min_age}岁）', 'error')
        return redirect(url_for('main.experiment_detail', id=experiment.id))
        
    if experiment.max_age and current_user.age > experiment.max_age:
        flash(f'您不满足实验的年龄要求（最大年龄：{experiment.max_age}岁）', 'error')
        return redirect(url_for('main.experiment_detail', id=experiment.id))
        
    if experiment.required_gender and experiment.required_gender != 'any' and current_user.gender != experiment.required_gender:
        gender_map = {'male': '男性', 'female': '女性', 'any': '不限'}
        flash(f'您不满足实验的性别要求（要求性别：{gender_map.get(experiment.required_gender, "不限")}）', 'error')
        return redirect(url_for('main.experiment_detail', id=experiment.id))
    
    # 创建参与记录
    participation = Participation(
        experiment_id=experiment.id,
        user_id=current_user.id,
        status='pending',
        started_at=datetime.utcnow()
    )
    db.session.add(participation)
    
    # 添加通知
    notification = Notification(
        user_id=current_user.id,
        title='成功加入实验',
        message=f'您已成功通过邀请码加入实验"{experiment.title}"。',
        type='experiment_joined'
    )
    db.session.add(notification)
    
    db.session.commit()
    
    flash('成功加入实验！', 'success')
    return redirect(url_for('main.experiment_detail', id=experiment.id))

@main.route('/join_by_code', methods=['POST'])
@login_required
def join_by_code():
    """通过表单中的邀请码加入实验"""
    # 管理员不能参与实验
    if current_user.role == 'admin':
        flash('管理员不能参与实验', 'error')
        return redirect(url_for('main.experiment'))
        
    invite_code = request.form.get('invite_code', '')
    
    # 查找对应的实验
    experiment = Experiment.query.filter_by(invite_code=invite_code).first()
    
    if not experiment:
        flash('无效的邀请码，请检查后重试。', 'error')
        return redirect(url_for('main.experiment'))
    
    # 检查实验状态
    if experiment.status != 'active':
        flash('该实验尚未开始招募，请等待管理员开启实验。', 'warning')
        return redirect(url_for('main.experiment'))
    
    # 检查是否为公开实验，如果是公开实验不需要邀请码
    if experiment.visibility == 'public':
        flash('这是一个公开实验，您可以直接参与，无需输入邀请码。', 'info')
        return redirect(url_for('main.experiment_detail', id=experiment.id))
    
    # 检查用户是否已经参与了该实验
    existing_participation = Participation.query.filter_by(
        experiment_id=experiment.id,
        user_id=current_user.id
    ).first()
    
    if existing_participation:
        flash('您已经参与了此实验。', 'info')
        return redirect(url_for('main.experiment_detail', id=experiment.id))
    
    # 检查是否满足参与要求
    if experiment.min_age and current_user.age < experiment.min_age:
        flash(f'您不满足实验的年龄要求（最小年龄：{experiment.min_age}岁）', 'error')
        return redirect(url_for('main.experiment'))
        
    if experiment.max_age and current_user.age > experiment.max_age:
        flash(f'您不满足实验的年龄要求（最大年龄：{experiment.max_age}岁）', 'error')
        return redirect(url_for('main.experiment'))
        
    if experiment.required_gender and experiment.required_gender != 'any' and current_user.gender != experiment.required_gender:
        gender_map = {'male': '男性', 'female': '女性', 'any': '不限'}
        flash(f'您不满足实验的性别要求（要求性别：{gender_map.get(experiment.required_gender, "不限")}）', 'error')
        return redirect(url_for('main.experiment'))
    
    # 创建参与记录
    participation = Participation(
        experiment_id=experiment.id,
        user_id=current_user.id,
        status='pending',
        started_at=datetime.utcnow()
    )
    db.session.add(participation)
    
    # 添加通知
    notification = Notification(
        user_id=current_user.id,
        title='成功加入实验',
        message=f'您已成功通过邀请码加入实验"{experiment.title}"。',
        type='experiment_joined'
    )
    db.session.add(notification)
    
    db.session.commit()
    
    flash(f'您已成功加入实验：{experiment.title}', 'success')
    return redirect(url_for('main.experiment_detail', id=experiment.id))

@main.route('/invitations')
@login_required
def my_invitations():
    """管理员查看所有邀请"""
    if current_user.role != 'admin':
        flash('只有管理员可以访问此页面', 'error')
        return redirect(url_for('main.index'))
    
    invitations = ExperimentInvitation.query.order_by(ExperimentInvitation.invited_at.desc()).all()
    status_map = {
        'pending': '待回应',
        'accepted': '已接受',
        'rejected': '已拒绝',
        'expired': '已过期',
        'cancelled': '已取消'
    }
    return render_template('main/invitations.html', invitations=invitations, status_map=status_map)

@main.route('/invitation/<int:id>/respond', methods=['POST'])
@login_required
def respond_to_invitation(id):
    """响应实验邀请"""
    invitation = ExperimentInvitation.query.get_or_404(id)
    if invitation.user_id != current_user.id:
        flash('无效的操作。', 'error')
        return redirect(url_for('main.notifications'))
    
    # 检查邀请是否已响应
    if invitation.status != 'pending':
        flash('此邀请已经被响应过。', 'warning')
        return redirect(url_for('main.notifications'))
    
    # 检查实验状态
    if invitation.experiment.status != 'active':
        flash('该实验尚未开始招募，请等待管理员开启实验。', 'warning')
        return redirect(url_for('main.notifications'))
    
    response = request.form.get('response')
    note = request.form.get('note')
    
    if response not in ['accept', 'reject']:
        flash('无效的响应。', 'error')
        return redirect(url_for('main.notifications'))
    
    if response == 'accept':
        # 检查是否满足参与要求
        if invitation.experiment.min_age and current_user.age < invitation.experiment.min_age:
            flash(f'您不满足实验的年龄要求（最小年龄：{invitation.experiment.min_age}岁）', 'error')
            return redirect(url_for('main.notifications'))
            
        if invitation.experiment.max_age and current_user.age > invitation.experiment.max_age:
            flash(f'您不满足实验的年龄要求（最大年龄：{invitation.experiment.max_age}岁）', 'error')
            return redirect(url_for('main.notifications'))
            
        if invitation.experiment.required_gender and invitation.experiment.required_gender != 'any' and current_user.gender != invitation.experiment.required_gender:
            gender_map = {'male': '男性', 'female': '女性', 'any': '不限'}
            flash(f'您不满足实验的性别要求（要求性别：{gender_map.get(invitation.experiment.required_gender, "不限")}）', 'error')
            return redirect(url_for('main.notifications'))
        
        # 检查是否已存在参与记录
        existing_participation = Participation.query.filter_by(
            user_id=current_user.id,
            experiment_id=invitation.experiment_id
        ).first()
        
        if not existing_participation:
            # 创建参与记录
            participation = Participation(
                user_id=current_user.id,
                experiment_id=invitation.experiment_id,
                status='pending'  # 初始状态为待开始
            )
            db.session.add(participation)
        
        # 接受邀请
        invitation.status = 'accepted'
        invitation.responded_at = datetime.utcnow()
        invitation.response_note = note
        
        # 创建通知给管理员
        notification = Notification(
            user_id=invitation.created_by_id,
            title='实验邀请已接受',
            message=f'用户 {current_user.username} 已接受实验"{invitation.experiment.title}"的邀请。',
            type='invitation_accepted'
        )
        db.session.add(notification)
        
        db.session.commit()
        flash('已接受实验邀请，您可以在"我的实验"中查看此实验。', 'success')
    else:
        # 拒绝邀请
        invitation.status = 'rejected'
        invitation.responded_at = datetime.utcnow()
        invitation.response_note = note
        
        # 创建通知给管理员
        notification = Notification(
            user_id=invitation.created_by_id,
            title='实验邀请已拒绝',
            message=f'用户 {current_user.username} 已拒绝实验"{invitation.experiment.title}"的邀请。',
            type='invitation_rejected'
        )
        db.session.add(notification)
        
        db.session.commit()
        flash('已拒绝实验邀请。', 'success')
    
    # 重定向到通知页面
    return redirect(url_for('main.notifications'))

@main.route('/invitation/<int:id>/cancel', methods=['POST'])
@login_required
def cancel_invitation(id):
    """管理员取消邀请"""
    if current_user.role != 'admin':
        flash('只有管理员可以取消邀请。', 'error')
        return redirect(url_for('main.index'))
    
    invitation = ExperimentInvitation.query.get_or_404(id)
    if invitation.cancel():
        db.session.commit()
        flash('已取消邀请。', 'success')
    else:
        flash('无法取消邀请，可能邀请已被响应。', 'error')
    
    return redirect(url_for('main.my_invitations'))

@main.route('/experiments')
@login_required
def experiments():
    """重定向到实验列表页面"""
    return redirect(url_for('main.experiment'))

@main.route('/main/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if current_user.role == 'admin':
        flash('管理员无需维护个人信息', 'info')
        return redirect(url_for('main.index'))
        
    form = ProfileForm()
    
    if form.validate_on_submit():
        try:
            # 转换毕业时间
            grad_date = date(int(form.graduation_year.data),
                           int(form.graduation_month.data),
                           1)  # 使用每月1号作为日期
            
            current_user.gender = form.gender.data
            current_user.age = int(form.age.data)
            current_user.school = form.school.data
            current_user.college = form.college.data
            current_user.graduation_date = grad_date
            current_user.phone = form.phone.data
            current_user.profile_completed = True
            
            db.session.commit()
            flash('个人信息已更新', 'success')
            
            # 检查是否是有效的实验参与者
            if not current_user.is_valid_participant():
                flash('注意：您的毕业时间已超过6个月，不符合实验参与条件', 'warning')
            
            return redirect(url_for('main.user_home'))  # 更新后直接进入用户首页
            
        except Exception as e:
            db.session.rollback()
            flash('更新失败，请重试', 'error')
    
    # GET请求或表单验证失败，显示当前信息
    if current_user.is_profile_complete():
        form.gender.data = current_user.gender
        form.age.data = str(current_user.age)
        form.school.data = current_user.school
        form.college.data = current_user.college
        if current_user.graduation_date:
            form.graduation_year.data = str(current_user.graduation_date.year)
            form.graduation_month.data = str(current_user.graduation_date.month)
        form.phone.data = current_user.phone
    
    return render_template('main/profile.html', form=form)

@main.route('/notifications')
@login_required
def notifications():
    """查看通知列表"""
    notifications = current_user.notifications.order_by(Notification.created_at.desc()).all()
    unread_count = current_user.notifications.filter_by(read=False).count()
    
    # 获取用户收到的所有邀请
    invitations = ExperimentInvitation.query.filter_by(user_id=current_user.id).all()
    # 创建邀请ID到邀请对象的映射
    invitations_dict = {invitation.id: invitation for invitation in invitations}
    
    return render_template('main/notifications.html', 
                         notifications=notifications,
                         unread_count=unread_count,
                         invitations_dict=invitations_dict)

@main.route('/notification/<int:id>/read', methods=['POST'])
@login_required
def mark_notification_read(id):
    """标记单个通知为已读"""
    notification = Notification.query.get_or_404(id)
    if notification.user_id != current_user.id:
        flash('无效的操作。', 'error')
        return redirect(url_for('main.notifications'))
    
    notification.read = True
    db.session.commit()
    return redirect(url_for('main.notifications'))

@main.route('/notifications/mark_all_read', methods=['POST'])
@login_required
def mark_all_read():
    """标记所有通知为已读"""
    current_user.notifications.filter_by(read=False).update({'read': True})
    db.session.commit()
    flash('所有通知已标记为已读。', 'success')
    return redirect(url_for('main.notifications'))

@main.route('/history_experiments')
@login_required
def history_experiments():
    """查看历史实验记录"""
    if current_user.role == 'admin':
        flash('管理员不能查看实验记录', 'warning')
        return redirect(url_for('main.experiment'))
    
    # 获取用户已完成的实验记录
    completed_participations = Participation.query.filter_by(
        user_id=current_user.id,
        status='completed'
    ).order_by(Participation.completed_at.desc()).all()
    
    # 获取用户进行中的实验记录
    ongoing_participations = Participation.query.filter_by(
        user_id=current_user.id,
        status='started'
    ).order_by(Participation.started_at.desc()).all()
    
    status_map = {
        'pending': '待开始',
        'started': '进行中',
        'completed': '已完成',
        'cancelled': '已取消'
    }
    
    return render_template('main/history_experiments.html',
                         completed_participations=completed_participations,
                         ongoing_participations=ongoing_participations,
                         status_map=status_map)

@main.route('/reservable_experiments')
@login_required
@profile_required
def reservable_experiments():
    """显示可预约的实验列表（未开始的公开实验）"""
    # 管理员不能预约实验
    if current_user.role == 'admin':
        flash('管理员不能预约实验', 'warning')
        return redirect(url_for('main.experiment'))
        
    # 检查并自动开启已到开启时间的实验
    check_auto_start_experiments()
    
    # 获取用户已参与的实验ID列表
    participations = Participation.query.filter_by(user_id=current_user.id).all()
    participation_experiment_ids = [p.experiment_id for p in participations]
    
    # 获取用户已预约的实验ID列表
    reservations = ExperimentReservation.query.filter_by(
        user_id=current_user.id, 
        status='pending'
    ).all()
    reservation_experiment_ids = [r.experiment_id for r in reservations]
    
    # 获取未开始的公开实验（状态为draft，可见性为public）
    reservable_experiments = Experiment.query.filter(
        Experiment.status == 'draft',  # 草稿状态（未开始）
        Experiment.deleted_at == None,  # 未删除
        ~Experiment.id.in_(participation_experiment_ids),  # 未参与
        ~Experiment.id.in_(reservation_experiment_ids),  # 未预约
        Experiment.visibility == 'public'  # 仅公开实验
    ).all()
    
    # 已预约的实验
    reserved_experiments = Experiment.query.join(ExperimentReservation).filter(
        ExperimentReservation.user_id == current_user.id,
        ExperimentReservation.status == 'pending',
        Experiment.deleted_at == None
    ).all()
    
    return render_template('main/reservable_experiments.html', 
                         reservable_experiments=reservable_experiments, 
                         reserved_experiments=reserved_experiments,
                         timedelta=timedelta)

@main.route('/experiment/<int:id>/reserve')
@login_required
@profile_required
def reserve_experiment(id):
    """预约未开始的公开实验"""
    # 管理员不能预约实验
    if current_user.role == 'admin':
        flash('管理员不能预约实验', 'error')
        return redirect(url_for('main.experiment'))
        
    experiment = Experiment.query.get_or_404(id)
    
    # 检查实验是否可预约（draft状态且可见性为public）
    if experiment.status != 'draft':
        flash('实验已开始招募，无需预约', 'warning')
        return redirect(url_for('main.available_experiments'))
    
    if experiment.visibility != 'public':
        flash('该实验不是公开实验，无法预约', 'warning')
        return redirect(url_for('main.reservable_experiments'))
    
    # 检查是否已经参与
    existing_participation = Participation.query.filter_by(
        experiment_id=id, 
        user_id=current_user.id
    ).first()
    
    if existing_participation:
        flash('您已经参与了这个实验', 'warning')
        return redirect(url_for('main.experiment_detail', id=id))
    
    # 检查是否已经预约
    existing_reservation = ExperimentReservation.query.filter_by(
        experiment_id=id, 
        user_id=current_user.id, 
        status='pending'
    ).first()
    
    if existing_reservation:
        flash('您已经预约了这个实验', 'info')
        return redirect(url_for('main.reservable_experiments'))
    
    # 检查是否满足年龄和性别要求
    if experiment.min_age and (not current_user.age or current_user.age < experiment.min_age):
        flash(f'您不满足实验的年龄要求（最小年龄：{experiment.min_age}岁）', 'error')
        return redirect(url_for('main.reservable_experiments'))
    
    if experiment.max_age and (not current_user.age or current_user.age > experiment.max_age):
        flash(f'您不满足实验的年龄要求（最大年龄：{experiment.max_age}岁）', 'error')
        return redirect(url_for('main.reservable_experiments'))
    
    if experiment.required_gender and experiment.required_gender != 'any' and current_user.gender != experiment.required_gender:
        gender_map = {'male': '男性', 'female': '女性', 'any': '不限'}
        flash(f'您不满足实验的性别要求（要求性别：{gender_map.get(experiment.required_gender, "不限")}）', 'error')
        return redirect(url_for('main.reservable_experiments'))
    
    # 创建预约记录
    reservation = ExperimentReservation(
        experiment_id=id,
        user_id=current_user.id
    )
    db.session.add(reservation)
    
    # 创建通知给用户
    notification = Notification(
        user_id=current_user.id,
        title='实验预约成功',
        message=f'您已成功预约实验"{experiment.title}"。实验开始招募后，系统将自动为您加入该实验。',
        type='experiment_reserved'
    )
    db.session.add(notification)
    
    db.session.commit()
    flash('实验预约成功！实验开始招募后将自动加入', 'success')
    return redirect(url_for('main.reservable_experiments'))

@main.route('/reservation/<int:id>/cancel', methods=['POST'])
@login_required
def cancel_reservation(id):
    """取消预约"""
    reservation = ExperimentReservation.query.get_or_404(id)
    
    # 检查是否是用户自己的预约
    if reservation.user_id != current_user.id:
        flash('无效的操作', 'error')
        return redirect(url_for('main.reservable_experiments'))
    
    # 检查预约状态
    if reservation.status != 'pending':
        flash('该预约无法取消', 'warning')
        return redirect(url_for('main.reservable_experiments'))
    
    # 获取实验信息以便后续通知使用
    experiment = reservation.experiment
    
    # 取消预约
    reservation.cancel()
    
    # 创建通知
    notification = Notification(
        user_id=current_user.id,
        title='实验预约已取消',
        message=f'您已取消预约实验"{experiment.title}"。',
        type='reservation_cancelled'
    )
    db.session.add(notification)
    
    db.session.commit()
    flash('预约已取消', 'success')
    return redirect(url_for('main.reservable_experiments')) 