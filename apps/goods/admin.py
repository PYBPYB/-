from django.contrib import admin
from django.core.cache import cache
from apps.goods.models import GoodsType, GoodsSKU, Goods, GoodsImage, IndexGoodsBanner, IndexTypeBanner, IndexPromotionBanner
# Register your models here.

# 父模板，
class BaseModeAdmin(admin.ModelAdmin):
    # 新增或更改表中的数据时调用
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)

        # 发出任务，让celery worker 重新生成首页静态页面(异步  管理员界面直接跳转，不会卡顿)
        from celery_tasks.development_tasks import generate_static_index_html
        generate_static_index_html.delay()

        # 请除首页的缓存数据
        cache.delete('index_page_data')


    # 删除表中数据时被调用
    def delete_model(self, request, obj):
        super().delete_model(request, obj)

        # 发出任务，让celery worker 重新生成首页静态页面(异步  管理员界面直接跳转，不会卡顿)
        from celery_tasks.development_tasks import generate_static_index_html
        generate_static_index_html.delay()

        # 请除首页的缓存数据
        cache.delete('index_page_data')

class GoodsAdmin(BaseModeAdmin):
    pass

class GoodsSKUAdmin(BaseModeAdmin):
    pass

class GoodsTypeAdmin(BaseModeAdmin):
    pass

class IndexGoodsBannerAdmin(BaseModeAdmin):
    pass

class IndexTypeBannerAdmin(BaseModeAdmin):
    pass


class IndexPromotionBannerAdmin(BaseModeAdmin):
    pass


admin.site.register(Goods, GoodsAdmin)
admin.site.register(GoodsSKU,GoodsSKUAdmin)
admin.site.register(GoodsType, GoodsTypeAdmin)
admin.site.register(IndexTypeBanner, IndexTypeBannerAdmin)
admin.site.register(IndexPromotionBanner, IndexPromotionBannerAdmin)
admin.site.register(IndexGoodsBanner, IndexGoodsBannerAdmin)



# admin.site.register(GoodsImage)
