from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, SubmitField, IntegerField, BooleanField, FieldList, DateTimeField, SelectMultipleField
from wtforms.validators import DataRequired, Length, Optional, URL, NumberRange
from datetime import datetime

class ExperimentForm(FlaskForm):
    # 基本信息
    title = StringField('实验标题', validators=[DataRequired(), Length(1, 128)])
    description = TextAreaField('实验描述', validators=[DataRequired()])
    duration = StringField('预计时长', validators=[DataRequired(), Length(1, 64)])
    reward = StringField('实验报酬', validators=[DataRequired(), Length(1, 64)])
    visibility = SelectField('可见性', choices=[
        ('private', '仅邀请'),
        ('public', '公开'),
        ('invitecode', '仅邀请码')
    ], validators=[Optional()])
    
    # 添加类别字段
    categories = SelectMultipleField('实验类别', choices=[
        ('认知实验', '认知实验'),
        ('社会心理学', '社会心理学'),
        ('临床心理学', '临床心理学'),
        ('发展心理学', '发展心理学'),
        ('教育心理学', '教育心理学'),
        ('其他', '其他')
    ], validators=[Optional()])
    
    # 实验要求
    min_age = IntegerField('最小年龄要求', validators=[Optional(), NumberRange(min=0, max=120)])
    max_age = IntegerField('最大年龄要求', validators=[Optional(), NumberRange(min=0, max=120)])
    required_gender = SelectField('性别要求', choices=[
        ('any', '不限'),
        ('male', '男性'),
        ('female', '女性')
    ], validators=[Optional()])
    requirements = TextAreaField('其他要求', validators=[Optional()])
    
    # 招募设置
    scheduled_start_time = DateTimeField('计划开始时间', 
                                       format='%Y-%m-%dT%H:%M',
                                       validators=[Optional()],
                                       description='选择计划开始时间')
    max_participants = IntegerField('最大参与人数', validators=[Optional(), NumberRange(min=1)])
    
    # 高级设置
    external_url = StringField('外部实验平台URL', validators=[Optional(), URL()])
    auto_approve = BooleanField('自动批准参与申请', default=False)
    send_reminder = BooleanField('发送参与提醒', default=True)
    allow_withdrawal = BooleanField('允许参与者中途退出', default=True)
    auto_close = BooleanField('招满自动关闭', default=False)
    notes = TextAreaField('管理员备注', validators=[Optional()])
    
    # 表单提交
    submit = SubmitField('保存')

class ProfileForm(FlaskForm):
    gender = SelectField('性别', 
                        choices=[('male', '男'), ('female', '女')],
                        validators=[DataRequired(message='请选择性别')])
    
    age = StringField('年龄',
                     validators=[DataRequired(message='请输入年龄'),
                               Length(min=1, max=3, message='请输入有效的年龄')])
    
    school = StringField('学校',
                        validators=[DataRequired(message='请输入学校名称'),
                                  Length(max=100, message='学校名称不能超过100个字符')])
    
    college = StringField('学院',
                         validators=[DataRequired(message='请输入学院名称'),
                                   Length(max=100, message='学院名称不能超过100个字符')])
    
    graduation_year = SelectField('毕业年份',
                                validators=[DataRequired(message='请选择毕业年份')])
    
    graduation_month = SelectField('毕业月份',
                                 choices=[(str(i), str(i)) for i in range(1, 13)],
                                 validators=[DataRequired(message='请选择毕业月份')])
    
    phone = StringField('电话号码',
                       validators=[DataRequired(message='请输入电话号码'),
                                 Length(min=11, max=11, message='请输入11位手机号码')])
    
    submit = SubmitField('保存')

    def __init__(self, *args, **kwargs):
        super(ProfileForm, self).__init__(*args, **kwargs)
        # 生成从当前年份开始的未来5年选项
        current_year = datetime.now().year
        self.graduation_year.choices = [
            (str(year), str(year)) for year in range(current_year, current_year + 6)
        ] 