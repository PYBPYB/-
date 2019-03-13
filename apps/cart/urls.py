from django.urls import path
from apps.cart.views import CartAddView, CartInfoView, CarUpdateView, CartDeleteView

urlpatterns = [
   path('add', CartAddView.as_view(), name='add'),  # 购物车记录添加
   path('update', CarUpdateView.as_view(), name='update'),  # 购物车记录更新
   path('delete', CartDeleteView.as_view(), name='delete'),  # 购物车记录删除
   path('', CartInfoView.as_view(), name='show'),  # 购物车页面显示
]
