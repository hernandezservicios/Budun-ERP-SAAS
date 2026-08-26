from django.urls import path

from . import views

app_name = "api_v1"

urlpatterns = [
    path("health/", views.HealthView.as_view(), name="health"),
    path("products/", views.ProductListView.as_view(), name="product_list"),
    path("products/<int:pk>/", views.ProductDetailView.as_view(), name="product_detail"),
    path("categories/", views.CategoryListView.as_view(), name="category_list"),
    path("inventory/", views.InventoryListView.as_view(), name="inventory_list"),
    path("inventory/low-stock/", views.InventoryLowStockView.as_view(), name="inventory_low_stock"),
    path("inventory/movements/", views.InventoryMovementsView.as_view(), name="inventory_movements"),
    path("inventory/serialized/", views.InventorySerializedView.as_view(), name="inventory_serialized"),
]
