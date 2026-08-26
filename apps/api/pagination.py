"""Paginación estándar de `/api/v1/` — `page`/`page_size` en la query
string, tope de `page_size` (nunca "sin límite", ver
`docs/api-inventory.md`). El sobre de respuesta (`meta.pagination`) es
armado por `responses.build_success_response`, no por esta clase
directamente — se usa solo para calcular `page`/`page_size`/`total`/
`next`/`previous`."""

from rest_framework.pagination import PageNumberPagination


class ApiV1Pagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_pagination_meta(self):
        return {
            "page": self.page.number,
            "page_size": self.get_page_size(self.request),
            "total": self.page.paginator.count,
            "next": bool(self.page.has_next()),
            "previous": bool(self.page.has_previous()),
        }
