from django.shortcuts import render, redirect
from django.views.generic import View
from django.urls import reverse
from django_redis import get_redis_connection
from django.http import JsonResponse
from django.db import transaction
from django.conf import settings

from datetime import datetime

from utils.mixin import LoginRequiredMixin
from apps.goods.models import GoodsSKU
from apps.order.models import OrderInfo, OrderGoods
from apps.user.models import AddressManager, Address

from alipay import AliPay
import os

# Create your views here.
# 显示提交订单页面 /order/place
# 接收参数 sku_ids
class OrderPlaceView(LoginRequiredMixin, View):

    def post(self, request):
        # 判断用户是否登录
        user = request.user
        if not user.is_authenticated:
            # 用户没有登录
            return redirect(reverse('user:login'))

        # 获取参数
        sku_ids = request.POST.getlist('sku_ids')

        # 数据校验
        if not sku_ids:
            # 跳转到购物车页面
            return redirect(reverse('cart:show'))

        # 获取 user用户 redis购物车的key
        conn = get_redis_connection('default')
        cart_key = 'cart_%d' % user.id

        skus = []  # 保存 需要购买的 商品信息
        total_count = 0  # 保存 需要购买的 商品的总件数
        total_price = 0  # 保存 需要购买的 商品的总价
        # 遍历sku_id 获取用户要购买的商品的信息
        for sku_id in sku_ids:
            # 根据商品的id获取商品的信息
            sku = GoodsSKU.objects.get(id=sku_id)
            # 获取用户所要购买的商品的数量
            count = conn.hget(cart_key, sku_id)
            # 计算商品的小计
            amount = sku.price * int(count)
            # 动态给 sku 增加属性 count(该商品数量) amount(小计)
            sku.count = int(count)
            sku.amount = amount
            # 追加
            skus.append(sku)
            # 累加计算 需要购买的 商品的总件数 商品的总价
            total_count += int(count)
            total_price += amount

        # 运费(实际开发的时候，属于一个子系统)
        transit_price = 10  # 写固定数目

        # 实付款
        total_pay = total_price + transit_price

        # 获取用户的收货地址
        addrs = Address.objects.filter(user=user)
        # 组织上下文
        sku_ids = ','.join(sku_ids)  # [1,2,3] ==> 1,2,3
        context = {
            'skus': skus,
            'total_count': total_count,
            'total_price': total_price,
            'transit_price':transit_price,
            'total_pay': total_pay,
            'addrs': addrs,
            'sku_ids': sku_ids,
        }
        # 使用模板
        return render(request, 'place_order.html', context)


# 传递过来的参数:地址id(addr_id)  支付方式(pay_method) 用户需要购买的商品id字符串（sku_ids）
# mysql事务：一组sql操作，要么全部执行完，要么不执行
# 高并发  悲观锁(进程锁)在冲突较少时  乐观锁(在更新数据时，进行判断，如果库存跟之前查询的不一样，则下单失败)
# 支付宝支付
class OrderCommitView1(View):
    @transaction.atomic  # Django自带的 事务 装饰器（创建 事务）
    def post(self, request):
        # 判断用户是否登录
        user = request.user
        if not user.is_authenticated:
            # 用户没有登录
            return JsonResponse({'res': 0, 'errmsg': '用户没有登录'})

        # 接收参数
        addr_id = request.POST.get('addr_id')
        pay_method = request.POST.get('pay_method')
        sku_ids = request.POST.get('sku_ids')  # 1,3,

        # 校验数据(数据完整性)
        if not all([addr_id, pay_method, sku_ids]):
            return JsonResponse({'res': 1, 'errmsg': '数据不完整'})

        # 校验支付方式
        if pay_method not in OrderInfo.PAY_METHODS.keys():
            return JsonResponse({'res': 2, 'errmsg': '非法的支付方式'})

        # 校验地址
        try:
            addr = Address.objects.get(id=addr_id)
        except Address.DoesNotExist:
            return JsonResponse({'res': 3, 'errmsg': '地址非法'})


        # todo:创建订单核心业务

        # 组织参数
        # 订单id：20190303190130+用户id
        order_id = datetime.now().strftime('%Y%m%d%H%M%S') + str(user.id)

        # 运费
        transit_price = 10

        # 总数目 和 总金额
        total_count = 0
        total_price = 0

        # 设置事务保存点
        save_id = transaction.savepoint()


        try:
            # todo: 向df_order_info表中添加一条订单信息
            order = OrderInfo.objects.create(order_id=order_id,
                                             user=user,
                                             addr=addr,
                                             pay_method=pay_method,
                                             total_count=total_count,
                                             total_price=total_price,
                                             transit_price=transit_price)
            # todo: 用户有几个商品就要向df_order_goods表中加入几条记录
            conn = get_redis_connection('default')
            cart_key = 'cart_%d' % user.id

            sku_ids = sku_ids.split(',')
            for sku_id in sku_ids:
                # 获取商品的信息
                try:  # 在查询商品时，就给该进程增加进程锁，只有进程释放时，才会开始下一个进程
                    sku = GoodsSKU.objects.select_for_update().get(id=sku_id)
                except:
                    transaction.savepoint_rollback(save_id)
                    return JsonResponse({'res': 4, 'errmsg': '商品不存在'})

                # 从redis中获取用户所要购买的商品的数量
                count = conn.hget(cart_key, sku_id)

                # todo: 判断商品的库存（别人可能比你先提交订单）
                if int(count) > sku.stock:
                    transaction.savepoint_rollback(save_id)
                    return JsonResponse({'res': 6, 'errmsg': '商品库存不足'})


                # todo: 向df_order_goods表中加入一条记录
                order_goods = OrderGoods.objects.create(order=order,
                                                        sku=sku,
                                                        count=count,
                                                        price=sku.price)

                # todo: 更新商品的库存和销量
                sku.stock -= int(count)
                sku.sales += int(count)
                sku.save()

                # todo: 雷家计算订单商品的 总数目 和 总金额
                amount = sku.price * int(count)
                total_count += int(count)
                total_price += amount

            # todo: 更新订单信息表中的 总数目 和 总金额
            order.total_count = total_count
            order.total_price = total_price
            order.save()
        except Exception as e:
            transaction.rollback(save_id)
            return JsonResponse({'res': 7, 'errmsg': '下单成功'})

        # 提交 事务
        transaction.savepoint_commit(save_id)

        # todo: 删除用户购物车中对应的记录
        conn.hdel(cart_key, *sku_ids)

        # 返回应答
        return JsonResponse({'res': 5, 'errmsg': '创建成功'})

# Django2.0+ 直接将 事务 直接改为 Read C0mmitted(读取提交内容)
# 乐观锁(在更新数据时，进行判断，如果库存跟之前查询的不一样，则下单失败)
class OrderCommitView(View):
    @transaction.atomic  # Django自带的 事务 装饰器（创建 事务）
    def post(self, request):
        # 判断用户是否登录
        user = request.user
        if not user.is_authenticated:
            # 用户没有登录
            return JsonResponse({'res': 0, 'errmsg': '用户没有登录'})

        # 接收参数
        addr_id = request.POST.get('addr_id')
        pay_method = request.POST.get('pay_method')
        sku_ids = request.POST.get('sku_ids')  # 1,3,

        # 校验数据(数据完整性)
        if not all([addr_id, pay_method, sku_ids]):
            return JsonResponse({'res': 1, 'errmsg': '数据不完整'})

        # 校验支付方式
        if pay_method not in OrderInfo.PAY_METHODS.keys():
            return JsonResponse({'res': 2, 'errmsg': '非法的支付方式'})

        # 校验地址
        try:
            addr = Address.objects.get(id=addr_id)
        except Address.DoesNotExist:
            return JsonResponse({'res': 3, 'errmsg': '地址非法'})


        # todo:创建订单核心业务

        # 组织参数
        # 订单id：20190303190130+用户id
        order_id = datetime.now().strftime('%Y%m%d%H%M%S') + str(user.id)

        # 运费
        transit_price = 10

        # 总数目 和 总金额
        total_count = 0
        total_price = 0

        # 设置事务保存点
        save_id = transaction.savepoint()


        try:
            # todo: 向df_order_info表中添加一条订单信息
            order = OrderInfo.objects.create(order_id=order_id,
                                             user=user,
                                             addr=addr,
                                             pay_method=pay_method,
                                             total_count=total_count,
                                             total_price=total_price,
                                             transit_price=transit_price)
            # todo: 用户有几个商品就要向df_order_goods表中加入几条记录
            conn = get_redis_connection('default')
            cart_key = 'cart_%d' % user.id

            sku_ids = sku_ids.split(',')
            for sku_id in sku_ids:
                for i in range(3):  # 尝试3次下单
                    # 获取商品的信息
                    try:
                        sku = GoodsSKU.objects.get(id=sku_id)
                    except:
                        transaction.savepoint_rollback(save_id)
                        return JsonResponse({'res': 4, 'errmsg': '商品不存在'})

                    # 从redis中获取用户所要购买的商品的数量
                    count = conn.hget(cart_key, sku_id)

                    # todo: 判断商品的库存（别人可能比你先提交订单,库存可能会在这里改变）
                    if int(count) > int(sku.stock):
                        transaction.savepoint_rollback(save_id)
                        return JsonResponse({'res': 6, 'errmsg': '商品库存不足'})


                    # todo: 更新商品的库存和销量
                    orgin_stock = sku.stock
                    new_stock = orgin_stock - int(count)
                    new_sales = sku.sales + int(count)

                    # print('user:%d time:%d stock:%d' % (user.id, i, sku.stock))
                    # import time
                    # time.sleep(10)

                    # update df_goods_sku set stock=new_stock,sales=new_sales
                    # where id=sku_id and stock = orgin_stock
                    # 返回受影响的行数(此条语句只影响一行，要么返回1【成功】，要么返回0【失败】)
                    res = GoodsSKU.objects.filter(id=sku_id, stock=orgin_stock).update(stock=new_stock, sales=new_sales)
                    if res == 0:
                        if i == 2:
                            # 尝试的第3次
                            transaction.savepoint_rollback(save_id)
                            return JsonResponse({'res': 7, 'errmsg': '下单失败2'})
                        continue

                    # 将下面的尝试代码移动到写入记录前面，防止重复记录
                    # todo: 向df_order_goods表中加入一条记录
                    OrderGoods.objects.create(order=order,
                                              sku=sku,
                                              count=count,
                                              price=sku.price)


                    # todo: 雷家计算订单商品的 总数目 和 总金额
                    amount = sku.price * int(count)
                    total_count += int(count)
                    total_price += amount

                    # 跳出循环
                    break

            # todo: 更新订单信息表中的 总数目 和 总金额
            order.total_count = total_count
            order.total_price = total_price
            order.save()
        except Exception as e:
            transaction.rollback(save_id)
            return JsonResponse({'res': 7, 'errmsg': '下单成功'})

        # 提交 事务
        transaction.savepoint_commit(save_id)

        # todo: 删除用户购物车中对应的记录
        conn.hdel(cart_key, *sku_ids)

        # 返回应答
        return JsonResponse({'res': 5, 'errmsg': '创建成功'})


# 订单支付
# /order/pay
class OrderPayView(View):

    def post(self, request):

        # 判断用户是否登录
        user = request.user
        if not user.is_authenticated:
            # 用户没有登录
            return JsonResponse({'res': 0, 'errmsg': '用户没有登录'})

        # 接受数据
        order_id = request.POST.get('order_id')

        # 校验数据
        if not order_id:
            return JsonResponse({'res': 1, 'errmsg': '无效的订单id'})

        try:
            order = OrderInfo.objects.get(order_id=order_id,
                                          user=user,
                                          # pay_method=3,  # 不管什么支付方式都改成支付宝支付
                                          order_status=1)
        except OrderInfo.DoesNotExist:
            return JsonResponse({'res': 1, 'errmsg': '订单错误'})

        # 业务处理：调用python sdk 使用支付宝支付订单
        # 初始化
        alipay = AliPay(
            appid='2016092500595996',  # 应用的id
            app_notify_url=None,  # 默认回调url
            app_private_key_path=os.path.join(settings.BASE_DIR, "apps/order/app_private_key.pem"),
            # 支付宝的公钥，验证支付宝回传消息使用，不是你自己的公钥
            alipay_public_key_path=os.path.join(settings.BASE_DIR, "apps/order/alipay_public_key.pem"),
            sign_type="RSA2",  # RSA 或者 RSA2
            debug=True  # 默认False  配合沙箱模式使用
            )

        # 调用电脑支付接口
        # 电脑网站支付，需要跳转到https://openapi.alipay.com/gateway.do? + order_string
        total_pay = order.total_price + order.transit_price  # 实际支付总金额
        order_string = alipay.api_alipay_trade_page_pay(
            out_trade_no=order_id,  # 订单id
            total_amount=str(0.01),  # 支付总金额
            subject="天天生鲜 %s" % order_id,
            return_url=None,  #
            notify_url=None  # 可选, 不填则使用默认notify url
        )
        # 返回应答
        pay_url = 'https://openapi.alipaydev.com/gateway.do?' + order_string
        return JsonResponse({'res': 3, 'pay_url': pay_url})

# 查询订单结果。。
class OrderCheckView(View):

    def post(self, request):
        # 判断用户是否登录
        user = request.user
        if not user.is_authenticated:
            # 用户没有登录
            return JsonResponse({'res': 0, 'errmsg': '用户没有登录'})

        # 接受数据
        order_id = request.POST.get('order_id')

        try:
            order = OrderInfo.objects.get(order_id=order_id, user=user)
        except OrderInfo.DoesNotExist:
            return redirect(reverse('user:order'))

        # 校验数据
        if not order_id:
            return JsonResponse({'res': 1, 'errmsg': '无效的订单id'})


        # 初始化
        alipay = AliPay(
            appid='2016092500595996',  # 应用的id
            app_notify_url=None,  # 默认回调url
            app_private_key_path=os.path.join(settings.BASE_DIR, "apps/order/app_private_key.pem"),
            # 支付宝的公钥，验证支付宝回传消息使用，不是你自己的公钥
            alipay_public_key_path=os.path.join(settings.BASE_DIR, "apps/order/alipay_public_key.pem"),
            sign_type="RSA2",  # RSA 或者 RSA2
            debug=True  # 默认False  配合沙箱模式使用
        )

        for i in range(120):
            import time
            time.sleep(1)
            try:
                result = alipay.api_alipay_trade_query(out_trade_no=order_id)
                trade_status = result.get('trade_status')
                code = result.get('code')
                if trade_status == 'TRADE_SUCCESS' and code == '10000':
                    # 修改 OrderInfo 中 订单状态(order_status） 和 支付编号（trade_no）
                    order.order_status = 4  # 去评价
                    order.trade_no = result.get('trade_no')
                    order.save()
                    return JsonResponse({'res': 3})
            except:
                continue

        sub_msg = result.get('sub_msg', '支付超时，请手动重新支付！')
        return JsonResponse({'res': 2, 'errmsg': sub_msg})

        # print('----->', result)
        """
         {'code': '10000', 'msg': 'Success',
          'buyer_logon_id': 'tqe***@sandbox.com', 
          'buyer_pay_amount': '0.00', 'buyer_user_id': '2088102177497820',
          'buyer_user_type': 'PRIVATE',
          'invoice_amount': '0.00', 'out_trade_no': '201903041026136',
          'point_amount': '0.00', 'receipt_amount': '0.00', 
          'send_pay_date': '2019-03-07 14:44:09', 
          'total_amount': '0.01', 
          'trade_no': '2019030722001497820200941406',
          'trade_status': 'TRADE_SUCCESS'}
        """


# 订单评论
class CommentView(LoginRequiredMixin, View):
    # 提供评论页面
    def get(self, request, order_id):
        user = request.user

        # 校验数据
        if not order_id:
            return redirect(reverse('user:order'))

        try:
            order = OrderInfo.objects.get(order_id=order_id, user=user)
        except OrderInfo.DoesNotExist:
            return redirect(reverse('user:order'))

        # 业务处理
        # 根据订单状态获取订单的状态标题
        order.status_name = OrderInfo.ORDER_STATUS[str(order.order_status)]

        # 获取订单商品信息
        order_skus = OrderGoods.objects.filter(order=order_id)
        for order_sku in order_skus:
            # 计算商品的小计
            amount = order_sku.count * order_sku.price
            # 动态给order_sku增加属性amount, 保存商品小计
            order_sku.amount = amount
        # 动态给order 增加属性 order_skus,保存订单信息
        order.order_skus = order_skus

        # 使用模板
        return render(request, 'order_comment.html', {'order': order})

    # 处理评论内容
    def post(self, request, order_id):
        user = request.user

        # 校验数据
        if not order_id:
            return redirect(reverse('user:order'))

        try:
            order = OrderInfo.objects.get(order_id=order_id, user=user)
        except OrderInfo.DoesNotExist:
            return redirect(reverse('user:order'))

        # 获取评论条数
        total_count = request.POST.get('total_count')
        total_count = int(total_count)

        for i in range(1, total_count+1):
            # 获取评论的商品id
            sku_id = request.POST.get('sku_%d' % i)  # sku_1 sku_2 sku_3
            # 获取评论的商品内容
            content = request.POST.get('content_%d' % i, '')  # content_1 content_2
            try:
                order_goods = OrderGoods.objects.get(order=order, sku_id=sku_id)
            except OrderGoods.DoesNotExist:
                continue

            order_goods.comment = content
            order_goods.save()

        order.order_status = 5  # 已完成
        order.save()

        return redirect(reverse('user:order', kwargs={'page': 1}))




