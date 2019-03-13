from django.shortcuts import render, redirect
from django.urls import reverse
from django.views.generic import View
from django.conf import settings
from django.http import HttpResponse
from django.core.paginator import Paginator
from django.contrib.auth import authenticate, login, logout

from apps.goods.models import GoodsSKU
from apps.order.models import OrderGoods, OrderInfo
from apps.user.models import User, Address

from itsdangerous import TimedJSONWebSignatureSerializer as Serializer  # 加密
from itsdangerous import SignatureExpired
from celery_tasks.tasks import send_register_active_email
from utils.mixin import LoginRequiredMixin
from django_redis import get_redis_connection
import re

# 注册
class RegisterView(View):

    def get(self, request):
        # 显示注册页面
        return render(request, 'register.html')

    def post(self, request):
        # 进行注册处理
        # 接受数据
        username = request.POST.get('user_name')
        password = request.POST.get('pwd')
        email = request.POST.get('email')
        allow = request.POST.get('allow')

        # 进行数据的校验
        if not all([username, password, email]):
            # 数据不完整
            return render(request, 'register.html',
                          {'errmsg': '数据不完整'})
        # 校验邮箱
        if not re.match(r'^[a-z0-9][\w.\-]*@[a-z0-9\-]+(\.[a-z]{2,5}){1,2}$', email):
            return render(request, 'register.html',
                          {'errmsg': '邮箱格式不正确'})

        if allow != 'on':
            return render(request, 'register.html',
                          {'errmsg': '请同意协议'})

        # 校验用户名是否重复
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            # 用户名不存在
            user = None
        if user:
            # 用户名已存在
            return render(request, 'register.html',
                          {'errmsg': '用户名已存在'})

        # 进行业务处理：进行用户注册
        user = User.objects.create_user(username, email, password)
        user.is_active = 0
        user.save()

        # 发送激活邮件，包含激活连接http://127.0.0.1:8000/user/id/ active
        # 激活链接中包含用户的身份信息,并且要进行加密

        # 加密用户的身份信息
        serialiser = Serializer(settings.SECRET_KEY, 3600)
        info = {'confirm': user.id}
        token = serialiser.dumps(info)  # bytes
        Token = token.decode('utf8')

        # 发邮件（celery<任务发出者-中间人-任务执行者>解决邮件发送过程中的页面等待问题）
        send_register_active_email.delay(email, username, Token)

        # 返回应答,跳转首页
        return redirect(reverse('goods:index'))  # 反向解析，需要目标设置的自己的 name属性

# 用户激活
class ActiveView(View):

    def get(self, request, token):
        # 进行用户激活
        # 进行解密，获取用户信息
        serialiser = Serializer(settings.SECRET_KEY, 3600)
        try:
            info = serialiser.loads(token)
            # 获取激活用户的id
            user_id = info['confirm']
            # 根据id获取用户信息
            user = User.objects.get(id=user_id)
            user.is_active = 1
            user.save()

            # 返回应答，跳转到登陆页面
            return redirect(reverse('user:login'))
        except SignatureExpired as e:
            # 激活链接已过期
            return HttpResponse('激活链接已过期')


# /user/login.html
class LoginView(View):
    """登录"""
    def get(self, request):
        # 显示登录页面
        if 'username' in request.COOKIES:
            username = request.COOKIES.get('username')
            checked = 'checked'
        else:
            username = ''
            checked = ''
        # 使用模板
        return render(request, 'login.html',
                      {'username': username,
                       'checked': checked})

    def post(self, request):
        # 登录校验
        # 接收数据
        username = request.POST.get('username')
        password = request.POST.get('pwd')
        # 校验数据
        if not all([username, password]):
            return render(request, 'login.html', {'errmsg': '数据不完整'})

        # 业务处理：登录校验
        # user = User.objects.get(username=username, password=password)
        user = authenticate(username=username, password=password)
        # print('------------------', user, '------------------')
        if user is not None:
            # 用户名、密码正确
            if user.is_active:
                # 用户已激活 <记录用户的登陆状态>
                login(request, user)

                # 获取登录后所要跳转的地址，默认跳转到首页（重定向）
                next_url = request.GET.get('next', reverse('goods:index'))  # None

                # 跳转到next_url
                # response = render(request, 'user_center_info.html')
                # response = render(reverse(next_url))  # 不是重定向
                response = redirect(next_url)

                # 判断是否需要记住用户名
                remember = request.POST.get('remember')

                if remember == 'on':
                    # 记住用户名
                    response.set_cookie('username', username, max_age=7*24*3600)
                else:
                    response.delete_cookie('username')
                # 返回 response
                return response
            else:
                # 用户没有激活
                return render(request, 'login.html', {'errmsg': '该账户未激活'})
        else:
            #  用户名或密码错误
            print(username, '---', password, user)
            return render(request, 'login.html', {'errmsg': '用户名或密码错误'})


class LogoutView(View):
    """退出登录"""
    def get(self, request):
        # 清除用户的session信息
        logout(request)
        return redirect(reverse('goods:index'))


class UserInfoView(LoginRequiredMixin, View):
    """用户中心-信息页"""

    def get(self, request):
        # request.user.is_authenticated()
        # 除了你给模板文件传递的模板变量之外，Django也会将request.user也传给模板文件

        # 获取用户的个人信息
        user = request.user
        address = Address.objects.get_default_address(user)


        # 获取用户的最近浏览
        # from redis import StrictRedis
        # StrictRedis(db='9')
        con = get_redis_connection('default')
        history_key = 'history_%d' % user.id

        # 获取用户浏览记录中最新5个商品的id
        sku_ids = con.lrange(history_key, 0, 5)

        # 从数据库中查询sku_ids中商品的具体信息
        # goods_li = GoodsSKU.objects.filter(id__in=sku_ids)
        goods_li = []
        for id in sku_ids:
            goods = GoodsSKU.objects.get(id=id)
            goods_li.append(goods)

        # 组织上下文
        context = {'page': 'user',
                   'address': address,
                   'goods_li': goods_li}

        return render(request, 'user_center_info.html', context)


class UserOrderView(LoginRequiredMixin, View):
    """用户中心-订单页"""
    def get(self, request, page):

        user = request.user
        # 获取用户的订单信息
        orders = OrderInfo.objects.filter(user=user).order_by('-create_time')

        # 循环遍历订单商品的信息
        for order in orders:

            # 查找本订单中所有的商品信息
            order_skus = OrderGoods.objects.filter(order_id=order.order_id)

            for order_sku in order_skus:
                amount = int(order_sku.count) * order_sku.price
                order_sku.amount = amount  # 该商品总价格

            # 保存订单状态
            order.status_name = OrderInfo.ORDER_STATUS[str(order.order_status)]

            # 动态给order增加skus属性
            order.order_skus = order_skus

        # 分页
        paginator = Paginator(orders, 2)

        # 获取第page页的内容(要进行数据校验，安全处理)
        try:
            page = int(page)
        except Exception as e:
            page = 1

        if page > paginator.num_pages:
            page = 1

        # 获取第page页的Page的实例化对象
        order_page = paginator.get_page(page)

        # todo: 进行页码的控制，页面上最多显示5个页码
        # 1、总页数小于5页，页面上显示所有页码
        # 2、如果当前页是前3页，显示1-5页
        # 3、如果当前页是后3页，显示后5页
        # 4、其他情况，显示当前页的前2页，当前页 和 当前页的后2页
        num_pages = paginator.num_pages
        if num_pages < 5:
            pages = range(1, num_pages + 1)
        elif page <= 3:
            pages = range(1, 6)
        elif num_pages - page <= 2:
            pages = range(num_pages - 4, num_pages + 1)
        else:
            pages = range(page - 2, page + 3)

        # 组织上下文
        context = {
            'order_page': order_page,
            'pages': pages,
            'page': 'order',
        }
        # 是用模板
        return render(request, 'user_center_order.html', context)


class UserAddressView(LoginRequiredMixin, View):
    """用户中心-地址页"""
    def get(self, request):
        # 获取登录用户对应的User对象
        user = request.user

        # 获取用户的默认收货地址
        # try:
        #     address = Address.objects.get(user=user, is_default=True)  # Model.Manger
        # except Address.DoesNotExist:
        #     # 不存在默认收获地址
        #     address = None
        address = Address.objects.get_default_address(user)

        # 使用模板
        return render(request, 'user_center_site.html',
                       {'page': 'address',
                        'address': address})

    def post(self, request):  # 地址的添加
        # 接收数据
        receiver = request.POST.get('receiver')
        addr = request.POST.get('addr')
        zip_code = request.POST.get('zip_code')
        phone = request.POST.get('phone')
        # 校验数据
        if not all([receiver, addr, phone]):
            return render(request, 'user_center_site.html',
                          {'errmsg': '数据不完整'})

        if not re.match(r'^1[3|4|5|7|8][0-9]{9}$', phone):
            return render(request, 'user_center_site.html',
                          {'errmsg': '手机格式不正确！'})


        # 如果用户存在收获地址，添加的地址则不作为默认地址
        # 获取登录用户对应的User对象
        user = request.user
        # try:
        #     address = Address.objects.get(user=user, is_default=True)
        # except Address.DoesNotExist:
        #     # 不存在默认收获地址
        #     address = None
        address = Address.objects.get_default_address(user)

        if address:
            is_default = False
        else:
            is_default = True

        # 业务处理：添加地址
        Address.objects.create(user=user,
                               receiver=receiver,
                               addr=addr,
                               zip_code=zip_code,
                               phone=phone,
                               is_default=is_default)

        # 返回应答,刷新地址页面
        return redirect(reverse('user:address'))
