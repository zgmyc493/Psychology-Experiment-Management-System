from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Email, Length, EqualTo, ValidationError
from flask import session
from app.models.user import User

class LoginForm(FlaskForm):
    username = StringField('用户名', validators=[DataRequired(message='请输入用户名')])
    password = PasswordField('密码', validators=[DataRequired(message='请输入密码')])
    captcha = StringField('验证码', validators=[DataRequired(message='请输入验证码')])
    remember_me = BooleanField('记住我')
    submit = SubmitField('登录')

    def validate_captcha(self, field):
        if 'captcha' not in session:
            return True
        if session.get('captcha', '').lower() != field.data.lower():
            session.pop('captcha', None)
            raise ValidationError('验证码错误，请重新输入')

class RegistrationForm(FlaskForm):
    username = StringField('用户名', validators=[
        DataRequired(message='请输入用户名'),
        Length(min=3, max=20, message='用户名长度必须在3到20个字符之间')
    ])
    email = StringField('邮箱', validators=[
        DataRequired(message='请输入邮箱'),
        Email(message='请输入有效的邮箱地址')
    ])
    password = PasswordField('密码', validators=[
        DataRequired(message='请输入密码'),
        Length(min=6, message='密码长度不能少于6个字符')
    ])
    password2 = PasswordField('确认密码', validators=[
        DataRequired(message='请再次输入密码'),
        EqualTo('password', message='两次输入的密码不一致')
    ])
    submit = SubmitField('注册')

    def validate_username(self, field):
        user = User.query.filter_by(username=field.data).first()
        if user:
            raise ValidationError('该用户名已被使用')

    def validate_email(self, field):
        user = User.query.filter_by(email=field.data).first()
        if user:
            raise ValidationError('该邮箱已被注册') 