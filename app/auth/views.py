from flask import render_template, redirect, request, url_for, flash, session, send_file
from flask_login import login_user, logout_user, login_required, current_user
from . import auth
from .forms import LoginForm, RegistrationForm
from app.models.user import User
from app import db
import random
import string
from PIL import Image, ImageDraw, ImageFont
import io

def generate_captcha(text, width=120, height=40):
    # 创建图像
    image = Image.new('RGB', (width, height), 'white')
    draw = ImageDraw.Draw(image)
    
    # 添加干扰线
    for i in range(5):
        x1 = random.randint(0, width)
        y1 = random.randint(0, height)
        x2 = random.randint(0, width)
        y2 = random.randint(0, height)
        draw.line([(x1, y1), (x2, y2)], fill='gray')
    
    # 添加干扰点
    for i in range(30):
        x = random.randint(0, width)
        y = random.randint(0, height)
        draw.point((x, y), fill='gray')
    
    # 绘制文字
    font_size = 30
    try:
        font = ImageFont.truetype('arial.ttf', font_size)
    except:
        font = ImageFont.load_default()
    
    text_width = font.getlength(text)
    text_height = font_size
    x = (width - text_width) // 2
    y = (height - text_height) // 2
    draw.text((x, y), text, font=font, fill='black')
    
    return image

@auth.route('/captcha')
def captcha():
    # 生成随机验证码
    characters = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    width = 120
    height = 44
    # 创建新图像
    image = Image.new('RGB', (width, height), color='white')
    # 创建画笔
    draw = ImageDraw.Draw(image)
    # 绘制背景
    for x in range(width):
        for y in range(height):
            if random.randint(0, 30) == 0:
                draw.point((x, y), fill='black')
    # 生成验证码文本
    code = ''.join(random.choice(characters) for _ in range(4))
    # 保存验证码到session
    session['captcha'] = code.lower()
    # 绘制文本
    try:
        font = ImageFont.truetype('arial.ttf', 36)
    except:
        font = ImageFont.load_default()
    for i, char in enumerate(code):
        x = 10 + i * 25
        y = random.randint(2, 8)
        draw.text((x, y), char, font=font, fill='black')
    # 添加干扰线
    for _ in range(3):
        x1 = random.randint(0, width)
        y1 = random.randint(0, height)
        x2 = random.randint(0, width)
        y2 = random.randint(0, height)
        draw.line((x1, y1, x2, y2), fill='gray')
    # 保存图像到内存
    buffer = io.BytesIO()
    image.save(buffer, format='JPEG')
    buffer.seek(0)
    return send_file(buffer, mimetype='image/jpeg')

@auth.route('/login', methods=['GET', 'POST'])
def login():
    # 如果用户已经登录，根据状态重定向
    if current_user.is_authenticated:
        if not current_user.is_profile_complete():
            return redirect(url_for('main.profile'))
        return redirect(url_for('main.user_home'))
        
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user is not None and user.verify_password(form.password.data):
            # 检查用户状态
            if not user.is_active:
                flash('您的账号已被禁用，请联系管理员。', 'error')
                return render_template('auth/login.html', form=form)
                
            # 如果是超级管理员，重定向到超级管理员登录页面
            if user.role == 'superadmin':
                flash('请使用超级管理员登录入口', 'warning')
                return redirect(url_for('superadmin.login'))
                
            # 登录用户
            login_user(user, remember=form.remember_me.data)
            user.update_last_login()
            db.session.commit()
            
            # 清除验证码session
            session.pop('captcha', None)
            
            # 新用户跳转到完善信息页面，老用户直接进入首页
            if not user.is_profile_complete():
                flash('请完善您的个人信息', 'warning')
                return redirect(url_for('main.profile'))
            return redirect(url_for('main.user_home'))
            
        flash('用户名或密码错误', 'error')
    elif form.errors:
        # 如果有表单验证错误（包括验证码错误），显示具体错误信息
        for field, errors in form.errors.items():
            for error in errors:
                if field == 'captcha':
                    flash('验证码错误', 'error')
                else:
                    flash(error, 'error')
                    
    return render_template('auth/login.html', form=form)

@auth.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
        
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(
            username=form.username.data,
            email=form.email.data
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        
        flash('注册成功！请登录后完善您的个人信息', 'success')
        return redirect(url_for('auth.login'))
        
    return render_template('auth/register.html', form=form)

@auth.route('/logout')
@login_required
def logout():
    logout_user()
    flash('您已退出登录', 'info')
    return redirect(url_for('main.index'))

@auth.route('/reset_password_request', methods=['GET', 'POST'])
def reset_password_request():
    if current_user.is_authenticated:
        flash('您已登录，如需修改密码请使用修改密码功能', 'info')
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        email = request.form.get('email')
        if not email:
            flash('请输入邮箱地址', 'error')
            return render_template('auth/reset_password_request.html')

        user = User.query.filter_by(email=email).first()
        if user:
            send_password_reset_email(user)
            flash('重置密码邮件已发送，请查收邮箱并按照提示操作', 'info')
            return redirect(url_for('auth.login'))
        flash('该邮箱未注册，请先注册账号', 'error')
    return render_template('auth/reset_password_request.html')

@auth.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        old_password = request.form.get('old_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        if not old_password or not new_password or not confirm_password:
            flash('请填写所有密码字段', 'error')
            return render_template('auth/change_password.html')
        
        if not current_user.verify_password(old_password):
            flash('修改失败：原密码错误', 'error')
            return render_template('auth/change_password.html')
            
        if new_password != confirm_password:
            flash('修改失败：两次输入的新密码不一致', 'error')
            return render_template('auth/change_password.html')
            
        if old_password == new_password:
            flash('修改失败：新密码不能与原密码相同', 'error')
            return render_template('auth/change_password.html')
            
        current_user.set_password(new_password)
        db.session.commit()
        flash('密码修改成功！请使用新密码登录', 'success')
        logout_user()
        return redirect(url_for('auth.login'))
        
    return render_template('auth/change_password.html')

@auth.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        flash('您已登录，如需修改密码请使用修改密码功能', 'info')
        return redirect(url_for('main.index'))
        
    user = User.verify_reset_password_token(token)
    if not user:
        flash('重置密码失败：链接无效或已过期', 'error')
        return redirect(url_for('auth.login'))
        
    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if not password or not confirm_password:
            flash('请填写所有密码字段', 'error')
            return render_template('auth/reset_password.html')
            
        if password != confirm_password:
            flash('重置失败：两次输入的密码不一致', 'error')
            return render_template('auth/reset_password.html')
            
        user.password = password
        db.session.commit()
        flash('密码重置成功！请使用新密码登录', 'success')
        return redirect(url_for('auth.login'))
        
    return render_template('auth/reset_password.html') 