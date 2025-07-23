from app import create_app, db
from app.models.user import User
from app.models.experiment import Experiment, Participation, ExperimentInvitation
from app.models.security import BlockedIP, SecurityLog, LoginAttempt
from app.models.settings import SystemSetting
import os

app = create_app()

def init_db():
    """初始化数据库，只在首次运行时执行"""
    with app.app_context():
        # 检查数据库文件是否存在（SQLite）
        db_path = os.path.join(os.path.dirname(__file__), 'app.db')
        is_first_run = not os.path.exists(db_path)
        
        # 对于MySQL，检查超级管理员用户是否存在
        if not is_first_run:
            try:
                superadmin = User.query.filter_by(role='superadmin').first()
                is_first_run = superadmin is None
            except Exception:
                is_first_run = True
        
        if is_first_run:
            print("首次运行，正在初始化数据库...")
            # 删除所有表并重新创建
            db.drop_all()
            db.create_all()
            
            # 创建超级管理员账号
            superadmin = User.query.filter_by(role='superadmin').first()
            if not superadmin:
                superadmin = User(
                    username='superadmin',
                    email='superadmin@example.com',
                    role='superadmin'
                )
                superadmin.set_password('superadmin@2024')
                db.session.add(superadmin)
                
                # 创建普通管理员账号
                admin = User(
                    username='admin',
                    email='admin@example.com',
                    role='admin'
                )
                admin.set_password('admin123')
                db.session.add(admin)
                
                # 创建系统设置
                settings = SystemSetting(
                    key='system_config',
                    value='default',
                    description='系统默认配置',
                    two_factor_auth=False,
                    password_expiry_days=90,
                    max_login_attempts=5
                )
                db.session.add(settings)
                
                db.session.commit()
                print("数据库初始化完成！")
                print("\n超级管理员账号信息：")
                print("------------------------")
                print("用户名：superadmin")
                print("密码：superadmin@2024")
                print("登录地址：/superadmin/login")
                print("------------------------")
                print("请登录后立即修改密码！\n")
                
                print("普通管理员账号信息：")
                print("------------------------")
                print("用户名：admin")
                print("密码：admin123")
                print("------------------------")
        else:
            print("数据库已存在，无需初始化。")

if __name__ == '__main__':
    init_db()  # 检查并在需要时初始化数据库
    app.run(debug=True) 