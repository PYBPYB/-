from django.urls import path
from apps.order.views import OrderPlaceView, OrderCommitView, OrderPayView, OrderCheckView, CommentView

urlpatterns = [
    path('place', OrderPlaceView.as_view(), name='place'),  # 显示提交订单页面
    path('commit', OrderCommitView.as_view(), name='commit'),  # 执行提交订单操作
    path('pay', OrderPayView.as_view(), name='pay'),  # 订单支付
    path('check', OrderCheckView.as_view(), name='ckeck'),  # 查询支付结果
    path('comment/<order_id>', CommentView.as_view(), name='comment'),  # 订单评论
]
