from django.urls import path
from django.contrib.auth.decorators import login_required
from apps.user.views import RegisterView, ActiveView, LoginView, UserInfoView, UserOrderView, UserAddressView, LogoutView

app_name = 'user'
urlpatterns = [
    path('register', RegisterView.as_view(), name='register'),  # 注册
    path('active/<token>', ActiveView.as_view(), name='active'),  # 用户激活

    path('login', LoginView.as_view(), name='login'),  # 登录页面
    path('logout', LogoutView.as_view(), name='logout'),  # 注销登录页面

    path('user', UserInfoView.as_view(), name='user'),  # 用户中心-信息页
    path('order/<page>/', UserOrderView.as_view(), name='order'),  # 用户中心-订单页
    path('address', UserAddressView.as_view(), name='address'),  # 用户中心-地址页
]
