from django.shortcuts import render, redirect
from django.views.generic import View
from django.urls import reverse
from django.http import JsonResponse
from django_redis import get_redis_connection

from apps.goods.models import GoodsSKU


# ajax 发起的请求都在后台，在浏览器中看不到效果，所以不能使用 mixin 判断登录状态
# /cart/add （添加购物车记录）
class CartAddView(View):
    # 购物车记录的添加
    def post(self, request):
        # 用户的登陆状态（未登录退出，登录了则继续）
        user = request.user
        if not user.is_authenticated:
            # 用户未登录
            return JsonResponse({'res': 0, 'errmsg': '请先登录'})
        # 接收数据
        sku_id = request.POST.get('sku_id')
        count = request.POST.get('count')

        # 校验数据(数据完整性 商品数量是否合格 商品是否存在 )
        if not all([sku_id, count]):
            return JsonResponse({'res': 1, 'errmsg': '数据不完整'})

        try:
            count = int(count)
        except Exception as e:
            return JsonResponse({'res': 2, 'errmsg': '商品数目出错'})

        try:
            sku = GoodsSKU.objects.get(id=sku_id)
        except GoodsSKU.DoesNotExist:
            return JsonResponse({'res': 3, 'errmsg': '商品不存在'})

        # 业务处理（添加购物车记录）
        # 先尝试获取购物车记录
        conn = get_redis_connection('default')
        cart_key = 'cart_%d' % user.id
        # 先尝试获取sku_id --> hget cart_key 属性
        cart_count = conn.hget(cart_key, sku_id)  # 如果拿不到，返回None
        if cart_count:  # 累计购物车中的商品数目
            count += int(cart_count)

        # 校验商品的库存
        if count > sku.stock:
            return JsonResponse({'res': 4, 'errmsg': '库存不足'})

        # 设置hash中cart_id对应的值（如果sku_id已经存在，更新数据;如果sku_id不存在，添加数据）
        conn.hset(cart_key, sku_id, count)

        # 计算用户购物车中商品的条目数量
        total_count = conn.hlen(cart_key)

        # 返回应答
        return JsonResponse({'res': 5, 'total_count': total_count, 'errmsg': '添加成功'})

# 购物车页面
class CartInfoView(View):

    def get(self, request):
        # 获取登陆的用户
        user = request.user
        if not user.is_authenticated:
            # 用户未登录
            return redirect(reverse('user:login'))
        # 获取用户购物车中的商品信息
        conn = get_redis_connection('default')
        # print(user.id)
        cart_key = 'cart_%d' % user.id
        # {'商品id': 商品数量，'商品id': 商品数量，。。。。。。}
        cart_dict = conn.hgetall(cart_key)

        skus = []
        total_count = 0  # 保存购物车中的宗商品数量
        total_price = 0  # 保存购物车中的商品总价
        # 便利获取商品的信息
        for sku_id, count in cart_dict.items():
            # 根据商品的id过去商品的信息
            sku = GoodsSKU.objects.get(id=sku_id)
            # 计算商品的小计
            amount = sku.price * int(count)

            # 动态给sku对象增加一个属性amount，保存商品的小计
            sku.amount = amount
            # 动态给sku对象增加一个属性amount，保存商品的数量
            sku.count = count.decode('utf8')
            # 添加
            skus.append(sku)
            # 雷家计算总商品数量 和 总价格
            total_count += int(count)
            total_price += amount

        # 组织上下文
        context = {
            'total_count': total_count,
            'total_price': total_price,
            'skus': skus,
        }
        # 使用模板
        return render(request, 'cart.html', context)


# 更新购物车记录(采用ajax post请求方式)==>需要传递的参数:商品id 更新的商品的数量(count)
class CarUpdateView(View):

    def post(self, request):
        user = request.user
        if not user.is_authenticated:
            # 用户未登录
            return JsonResponse({'res': 0, 'errmsg': '请先登录'})

        # 接收数据
        sku_id = request.POST.get('sku_id')
        count = request.POST.get('count')

        # 校验数据(数据完整性 商品数量是否合格 商品是否存在 )
        if not all([sku_id, count]):
            return JsonResponse({'res': 1, 'errmsg': '数据不完整'})

        try:
            count = int(count)
        except Exception as e:
            return JsonResponse({'res': 2, 'errmsg': '商品数目出错'})

        try:
            sku = GoodsSKU.objects.get(id=sku_id)
        except GoodsSKU.DoesNotExist:
            return JsonResponse({'res': 3, 'errmsg': '商品不存在'})

        # 处理业务(更新购物车记录)
        conn = get_redis_connection('default')
        cart_key = 'cart_%d' % user.id

        # 校验商品的库存
        if count > sku.stock:
            return JsonResponse({'res': 4, 'errmsg': '库存不足'})
        # 设置hash中cart_id对应的值（如果sku_id已经存在，更新数据;如果sku_id不存在，添加数据）

        # 更新
        conn.hset(cart_key, sku_id, count)

        # 计算用户购物车中商品的总件数
        total_count = 0
        for val in conn.hvals(cart_key):
            total_count += int(val)

        # 返回应答
        return JsonResponse({'res': 5, 'total_count': total_count, 'errmsg': '更新成功'})

# 删除购物车记录
# 采用ajax post请求
# /cart/delete
class CartDeleteView(View):

    def post(self, request):
        user = request.user
        if not user.is_authenticated:
            # 用户未登录
            return JsonResponse({'res': 0, 'errmsg': '请先登录'})

        # 接收数据
        sku_id = request.POST.get('sku_id')

        # 数据校验
        if not sku_id:
            return JsonResponse({'res': 1, 'errmsg': '无效的商品id'})

        try:
            sku = GoodsSKU.objects.get(id=sku_id)
        except GoodsSKU.DoesNotExist:
            return JsonResponse({'res': 2, 'errmsg': '商品不存在'})

        # 业务处理：删除购物车记录
        conn = get_redis_connection('default')
        cart_key = 'cart_%d' % user.id

        # 删除
        conn.hdel(cart_key, sku_id)
        # 计算用户购物车中商品的总件数
        total_count = 0
        for val in conn.hvals(cart_key):
            total_count += int(val)

        # 返回应答
        return JsonResponse({'res': 3, 'total_count': total_count, 'messmsg': '删除成功'})



