#!/usr/bin/python
from celery import Celery
from django.conf import settings
from django.core.mail import send_mail
from django.template import loader, RequestContext

from django_redis import get_redis_connection

# 在任务处理者一端加上这几句,初始化
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dailyfresh.settings.production')
django.setup()

# from apps.goods.models import *  # 这个东西没用他，也会阻止celery启动？？？？
# 这个要写到django.setup()下面，必须先Django初始化
from apps.goods.models import IndexGoodsBanner, IndexPromotionBanner, IndexTypeBanner, GoodsType

# 创建对象
app = Celery('celery_tasks.tasks', broker='redis://127.0.0.1:6379/8')

# 定义任务函数,注册时发送激活邮件
@ app.task
def send_register_active_email(to_email, username, token):
    # 发邮件
    sbuject = '天天生鲜欢迎信息'
    message = ''
    sender = settings.EMAIL_FROM
    receiver = [to_email]
    html_message = '''
    <h1>%s,欢迎您成为天天生鲜注册会员</h1>
    请点击下面的链接激活您的帐户：<br />
    <a href='http://47.100.227.176:8000/user/active/%s'>http://47.100.227.176:8000/user/active/%s</a>
    ''' % (username, token, token)
    # 标题 正文（非html文件） 发件人邮箱 收件人列表 正文（html文件）
    send_mail(sbuject, message, sender, receiver, html_message=html_message)
    # time.sleep(5)

# 产生首页静态页面
@ app.task
def generate_static_index_html():

    # 获取商品的种类信息
    types = GoodsType.objects.all()

    # 获取首页轮播商品信息
    goods_banners = IndexGoodsBanner.objects.all().order_by('index')

    # 获取首页促销活动信息
    promotion_bannsers = IndexPromotionBanner.objects.all().order_by('index')

    # 获取首页分类商品展示信息
    for type in types:  # GoodsType
        # 获取type种类首页分类商品的图片展示信息
        image_banners = IndexTypeBanner.objects.filter(type=type, display_type=1).order_by('index')
        # 获取type种类首页分类商品的文字展示信息
        title_banners = IndexTypeBanner.objects.filter(type=type, display_type=0).order_by('index')

        # 动态给type增加属性，分别保存首页分类商品的图片展示信息和文字展示信息
        type.image_banners = image_banners
        type.title_banners = title_banners

    # 组织上下文
    context = {
        'types': types,
        'goods_banners': goods_banners,
        'promotion_banners': promotion_bannsers,
    }

    # 使用模板
    # return render(request, 'index.html', context)  # HttpResponse
    # 1、加载模板文件,返回模板文件
    temp = loader.get_template('static_index.html')
    # # 2、定义模板上下文
    # context = RequestContext(request, context)
    # 3、模板渲染
    static_index_html = temp.render(context)
    # 4、生成首页对应静态文件
    save_path = os.path.join(settings.BASE_DIR, 'static/index.html')
    with open(save_path, 'w') as f:
        f.write(static_index_html)
