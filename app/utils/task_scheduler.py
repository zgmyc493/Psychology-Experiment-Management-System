from flask import current_app
from datetime import datetime, timedelta
from app.models.experiment import Experiment
from app.models.notification import Notification
from app import db
import threading
import time
import pytz
from time import sleep

def check_experiments(app):
    """定期检查实验状态的后台任务，接收app对象作为参数"""
    # 使用应用的上下文而不是current_app
    with app.app_context():
        print("[任务调度器] 成功创建应用上下文")
        
        # 记录上次检查时间
        last_check_time = datetime.utcnow()
        print(f"[任务调度器] 开始运行，初始时间: {last_check_time}")
        
        while True:
            try:
                # 获取当前UTC时间
                current_time = datetime.utcnow()
                
                # 转换为北京时间用于显示
                beijing_tz = pytz.timezone('Asia/Shanghai')
                beijing_time = datetime.now(pytz.utc).astimezone(beijing_tz)
                
                # 计算距离上次检查的时间间隔（秒）
                seconds_since_last_check = (current_time - last_check_time).total_seconds()
                
                # 只有在距离上次检查超过1秒时才进行检查
                # 这避免CPU满负荷运行同时保证响应及时性
                if seconds_since_last_check >= 1:
                    print(f"[任务调度器] 当前UTC时间: {current_time}")
                    print(f"[任务调度器] 当前北京时间: {beijing_time}")
                    
                    # 查找所有需要自动开启的实验
                    # 注意：数据库中存储的是UTC时间，所以直接比较即可
                    experiments_to_check = Experiment.query.filter(
                        Experiment.status == 'draft',
                        Experiment.scheduled_start_time != None,
                        Experiment.scheduled_start_time <= current_time  # 确保只查找应该开始的实验
                    ).all()
                    
                    if experiments_to_check:
                        print(f"[任务调度器] 找到 {len(experiments_to_check)} 个应该开始的草稿实验")
                    
                        # 开启所有满足条件的实验
                        for exp in experiments_to_check:
                            # 显示时间信息，包括UTC和北京时间
                            if exp.scheduled_start_time:
                                beijing_start_time = exp.scheduled_start_time + timedelta(hours=8)
                            else:
                                beijing_start_time = "未设置"
                            
                            print(f"[任务调度器] 准备开启实验: ID={exp.id}, 标题={exp.title}")
                            print(f"[任务调度器] 计划时间(UTC): {exp.scheduled_start_time}")
                            print(f"[任务调度器] 计划时间(北京): {beijing_start_time}")
                            
                            # 开启实验
                            exp.status = 'active'
                            print(f"[任务调度器] 实验状态已更改为: active")
                            
                            # 创建通知给管理员
                            notification = Notification(
                                user_id=exp.creator_id,
                                title='实验自动开启',
                                message=f'您的实验 "{exp.title}" 已按计划自动开启招募。',
                                type='experiment_auto_started'
                            )
                            db.session.add(notification)
                        
                        # 提交所有更改
                        db.session.commit()
                        print(f"[任务调度器] 成功自动开启了 {len(experiments_to_check)} 个实验")
                    else:
                        # 查找所有设置了计划时间的草稿实验，用于调试
                        future_experiments = Experiment.query.filter(
                            Experiment.status == 'draft',
                            Experiment.scheduled_start_time != None
                        ).all()
                        
                        if future_experiments:
                            print(f"[任务调度器] 找到 {len(future_experiments)} 个设置了计划时间的草稿实验")
                            
                            # 打印每个实验的信息，用于调试
                            for exp in future_experiments:
                                if exp.scheduled_start_time:
                                    beijing_start_time = exp.scheduled_start_time + timedelta(hours=8)
                                    time_diff = exp.scheduled_start_time - current_time
                                    
                                    print(f"[任务调度器] 实验ID={exp.id}, 标题={exp.title}")
                                    print(f"[任务调度器] 计划时间(UTC): {exp.scheduled_start_time}")
                                    print(f"[任务调度器] 计划时间(北京): {beijing_start_time}")
                                    print(f"[任务调度器] 距离开始还有: {time_diff}")
                        else:
                            print("[任务调度器] 没有找到设置了计划时间的草稿实验")
                    
                    # 更新上次检查时间
                    last_check_time = current_time
                
                # 短暂暂停以避免CPU占用过高
                # 这个暂停非常短，几乎不会影响响应速度
                sleep(0.1)
                
            except Exception as e:
                print(f"[任务调度器] 自动开启实验时出错: {str(e)}")
                import traceback
                print(traceback.format_exc())
                db.session.rollback()
                # 出错后暂停一小段时间避免错误持续产生
                sleep(1)

def init_app(app):
    """初始化任务调度器"""
    print("[任务调度器] 正在启动自动实验状态检查器...")
    
    # 创建后台线程运行任务调度器，传递app实例
    thread = threading.Thread(target=check_experiments, args=(app,), daemon=True, name="ExperimentChecker")
    thread.start()
    
    print("[任务调度器] 已启动自动实验状态检查器") 