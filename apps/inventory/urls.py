from django.urls import path

from . import views

app_name = "inventory"

urlpatterns = [
    path("categorias/", views.CategoryListView.as_view(), name="category_list"),
    path("categorias/nueva/", views.CategoryCreateView.as_view(), name="category_create"),
    path("categorias/<int:pk>/editar/", views.CategoryUpdateView.as_view(), name="category_update"),
    path("categorias/<int:pk>/eliminar/", views.CategoryDeleteView.as_view(), name="category_delete"),
    path("productos/", views.ProductListView.as_view(), name="product_list"),
    path("productos/nuevo/", views.ProductCreateView.as_view(), name="product_create"),
    path("productos/<int:pk>/", views.ProductDetailView.as_view(), name="product_detail"),
    path("productos/<int:pk>/editar/", views.ProductUpdateView.as_view(), name="product_update"),
    path("productos/<int:pk>/desactivar/", views.ProductDeactivateView.as_view(), name="product_deactivate"),
    path("productos/<int:pk>/entrada/", views.StockInView.as_view(), name="stock_in"),
    path("productos/<int:pk>/salida/", views.StockOutView.as_view(), name="stock_out"),
    path("productos/<int:pk>/ajuste/", views.StockAdjustmentView.as_view(), name="stock_adjustment"),
]
