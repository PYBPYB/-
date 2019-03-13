from django.shortcuts import render, redirect
from django.urls import reverse
from django.views.generic import View
from django.core.cache import cache
from django.core.paginator import Paginator  # 进行分页操作
from apps.goods.models import *
from apps.order.models import OrderGoods
from django_redis import get_redis_connection


# 主页
class IndexView(View):

    def get(self, request):

        # 尝试从缓存中获取数据
        context = cache.get('index_page_data')

        if context is None:
            print('设置缓存。。')
            # 缓存中没有数据
            # 获取商品的种类信息
            types = GoodsType.objects.all()
            # 获取首页轮播商品信息
            goods_banners = IndexGoodsBanner.objects.all().order_by('index')
            # 获取首页促销活动信息
            promotion_bannsers = IndexPromotionBanner.objects.all().order_by('index')
            # 获取首页分类商品展示信息
            for type in types:  # GoodsType
                # 获取type种类首页分类商品的图片展示信息（下面图片区展示的商品）
                image_banners = IndexTypeBanner.objects.filter(type=type, display_type=1).order_by('index')
                # 获取type种类首页分类商品的文字展示信息（标题旁边的商品展示）
                title_banners = IndexTypeBanner.objects.filter(type=type, display_type=0).order_by('index')

                # print('---------->', image_banners, title_banners)
                # 动态给type增加属性，分别保存首页分类商品的图片展示信息和文字展示信息
                type.image_banners = image_banners
                type.title_banners = title_banners

            context = {
                'types': types,
                'goods_banners': goods_banners,
                'promotion_banners': promotion_bannsers,
                'cart_count': 0,
            }

            # 设置缓存(key  value timeout)
            cache.set('index_page_data', context, 3600)

        # 获取用户购物车记录(不能设置在缓存中，应该每次加载都获取用户的购物车信息)
        user = request.user
        cart_count = 0
        if user.is_authenticated:
            # 用户已登录
            conn = get_redis_connection('default')
            cart_key = 'cart_%d' % user.id
            cart_count = conn.hlen(cart_key)  # 获取商品种类数目

        context['cart_count'] = cart_count

        # 使用模板
        return render(request, 'index.html', context)


# 详情页
class DetailView(View):

    def get(self, request, goods_id):
        # 查找该商品sku信息
        try:
            sku = GoodsSKU.objects.get(id=goods_id)
        except GoodsSKU.DoesNotExist:
            # 商品不存在
            return redirect(reverse('goods：index'))

        # 获取商品的分类信息
        types = GoodsType.objects.all()

        # 获取商品的评论信息
        sku_orders = OrderGoods.objects.filter(sku=sku).exclude(comment='')  # 排除(exclude)为空的数据

        # 获取新品信息
        new_skus = GoodsSKU.objects.filter(type=sku.type).order_by('-create_time')[:2]

        # 获取同一个SPU的其他规格商品
        same_spu_skus = GoodsSKU.objects.filter(goods=sku.goods).exclude(id=goods_id)

        # 获取用户购物车中商品的数目
        user = request.user
        cart_count = 0
        if user.is_authenticated:
            # 用户已登录
            conn = get_redis_connection('default')
            cart_key = 'cart_%d' % user.id
            cart_count = conn.hlen(cart_key)

            # 添加用户的历史浏览记录（用户最新浏览的商品id从列表左侧插入，在redis中用列表格式存储）
            # 去重
            conn = get_redis_connection('default')
            history_key = 'history_%d' % user.id
            conn.lrem(history_key, 0, goods_id)  # 移除列表中的goods_id
            # 2 将 goods_id 从列表的左侧插入
            conn.lpush(history_key, goods_id)
            # 只用保存用户最新浏览的5条信息
            conn.ltrim(history_key, 0, 4)


        # 组织上下文
        context = {
            'sku': sku,
            'types': types,
            'sku_orders': sku_orders,
            'new_skus': new_skus,
            'same_spu_skus': same_spu_skus,
            'cart_count': cart_count,
        }

        # 使用模板
        return render(request, 'detail.html', context)


# 显示列表页面（种类id 页码 排序方式）
# restful api-> 请求一种资源
# /list？type_di=种类id&page=页码&sort=排序方式
# /list/种类id/页码/排序方式
# /list/种类id/页码？sort=排序方式
class ListView(View):

    def get(self, request, goods_type_id, page):

        # 获取商品的分类信息(数据校验)
        try:
            type = GoodsType.objects.get(id=goods_type_id)
        except GoodsType.DoesNotExist:
            return redirect(reverse('goods:index'))

        # 获取商品的分类信息
        types = GoodsType.objects.all()

        # 获取新品信息
        new_skus = GoodsSKU.objects.filter(id=goods_type_id).order_by('-create_time')[:2]

        # 获取排序方式
        # sort=default 按照默认id排序
        # sort=price 价格排序
        # sort=hot 销量排序
        sort = request.GET.get('sort')
        if sort == 'price':
            skus = GoodsSKU.objects.filter(type=type).order_by('price')
        elif sort == 'hot':
            skus = GoodsSKU.objects.filter(type=type).order_by('-sales')
        else:
            skus = GoodsSKU.objects.filter(type=type).order_by('-id')

        # 对数据进行分页
        paginator = Paginator(skus, 1)

        # 获取第page页的内容(要进行数据校验，安全处理)
        try:
            page = int(page)
        except Exception as e:
            page = 1

        if page > paginator.num_pages:
            page = 1

        # 获取第page页的Page的实例化对象
        skus_page = paginator.get_page(page)

        # todo: 进行页码的控制，页面上最多显示5个页码
        # 1、总页数小于5页，页面上显示所有页码
        # 2、如果当前页是前3页，显示1-5页
        # 3、如果当前页是后3页，显示后5页
        # 4、其他情况，显示当前页的前2页，当前页 和 当前页的后2页
        num_pages = paginator.num_pages
        if num_pages < 5:
            pages = range(1, num_pages+1)
        elif page <= 3:
            pages = range(1, 6)
        elif num_pages - page <= 2:
            pages = range(num_pages-4, num_pages+1)
        else:
            pages = range(page-2, page+3)

        # 获取用户购物车中商品的数目
        user = request.user
        cart_count = 0
        if user.is_authenticated:
            # 用户已登录
            conn = get_redis_connection('default')
            cart_key = 'cart_%d' % user.id
            cart_count = conn.hlen(cart_key)

        # 组织上下文
        context = {
            'type': type,  # 该分页商品类型
            'types': types,  # 所有商品类型
            'new_skus': new_skus,  # 新品推荐
            'skus_page': skus_page,  # 该分页商品
            'pages': pages,  # 分页格式
            'cart_count': cart_count,  # 购物车信息
            'sort': sort
        }

        return render(request, 'list.html', context)

