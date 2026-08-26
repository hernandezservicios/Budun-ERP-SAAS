from django.urls import path

from . import catalog_views

app_name = "catalog"

urlpatterns = [
    path("search/", catalog_views.CatalogSearchView.as_view(), name="search"),
    path("products/", catalog_views.CatalogProductListView.as_view(), name="product_list"),
    path("products/<int:pk>/", catalog_views.CatalogProductDetailView.as_view(), name="product_detail"),
    path("availability/", catalog_views.CatalogAvailabilityView.as_view(), name="availability"),
    path("variants/", catalog_views.CatalogVariantsView.as_view(), name="variants"),
    path("media/", catalog_views.CatalogMediaListView.as_view(), name="media_list"),
    path("media/<uuid:public_id>/", catalog_views.CatalogMediaFileView.as_view(), name="media_file"),
]
