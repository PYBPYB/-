"""dailyfresh URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import re_path, include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    re_path(r'^tinymce/', include('tinymce.urls')),  # 富文本编辑器
    re_path(r'^search', include('haystack.urls'), name='haystack_search'),  # 全文检索框架
    re_path(r'^user/', include(('apps.user.urls', 'apps'), namespace='user')),  # 用户模块
    re_path(r'^order/', include(('apps.order.urls', 'apps'), namespace='order')),  # 订单模块
    re_path(r'^cart/', include(('apps.cart.urls', 'apps'), namespace='cart')),  # 购物车模块
    re_path(r'^', include(('apps.goods.urls', 'apps'), namespace='goods')),  # 商品模块

]