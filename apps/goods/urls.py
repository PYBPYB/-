from django.urls import path
from apps.goods import views

app_name = 'goods'
urlpatterns = [
   path('detail/<goods_id>', views.DetailView.as_view(), name='detail'),  # 详情页面
   path('list/<goods_type_id>/<page>/', views.ListView.as_view(), name='list'),  # 列表页面
   path('', views.IndexView.as_view(), name='index'),  # 主页
]
