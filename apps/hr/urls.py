from django.urls import path

from . import views

app_name = "hr"

urlpatterns = [
    # Empleados
    path("empleados/", views.EmployeeListView.as_view(), name="employee_list"),
    path("empleados/nuevo/", views.EmployeeCreateView.as_view(), name="employee_create"),
    path("empleados/<int:pk>/", views.EmployeeDetailView.as_view(), name="employee_detail"),
    path("empleados/<int:pk>/editar/", views.EmployeeEditView.as_view(), name="employee_edit"),
    path("empleados/<int:pk>/estado/", views.EmployeeStatusChangeView.as_view(), name="employee_status_change"),
    # Contratos
    path("empleados/<int:pk>/contratos/nuevo/", views.EmploymentContractCreateView.as_view(), name="contract_create"),
    path("empleados/<int:pk>/contratos/<int:contract_pk>/terminar/", views.EmploymentContractTerminateView.as_view(), name="contract_terminate"),
    # Documentos
    path("empleados/<int:pk>/documentos/subir/", views.EmployeeDocumentUploadView.as_view(), name="employee_document_upload"),
    path("empleados/<int:pk>/documentos/<int:document_pk>/eliminar/", views.EmployeeDocumentDeleteView.as_view(), name="employee_document_delete"),
    path("empleados/<int:pk>/documentos/<int:document_pk>/descargar/", views.EmployeeDocumentDownloadView.as_view(), name="employee_document_download"),
    # Asistencia
    path("empleados/<int:pk>/asistencia/entrada/", views.AttendanceCheckInView.as_view(), name="attendance_check_in"),
    path("empleados/<int:pk>/asistencia/<int:attendance_pk>/salida/", views.AttendanceCheckOutView.as_view(), name="attendance_check_out"),
    # Ausencias
    path("empleados/<int:pk>/ausencias/solicitar/", views.LeaveRequestView.as_view(), name="leave_request"),
    path("empleados/<int:pk>/ausencias/<int:leave_pk>/aprobar/", views.LeaveApproveView.as_view(), name="leave_approve"),
    path("empleados/<int:pk>/ausencias/<int:leave_pk>/rechazar/", views.LeaveRejectView.as_view(), name="leave_reject"),
    path("empleados/<int:pk>/ausencias/<int:leave_pk>/cancelar/", views.LeaveCancelView.as_view(), name="leave_cancel"),
    # Incidentes
    path("empleados/<int:pk>/incidentes/reportar/", views.IncidentReportView.as_view(), name="incident_report"),
    path("empleados/<int:pk>/incidentes/<int:incident_pk>/actualizar/", views.IncidentUpdateStatusView.as_view(), name="incident_update_status"),
    # Departamentos y Cargos
    path("departamentos/", views.DepartmentListView.as_view(), name="department_list"),
    path("departamentos/<int:pk>/activar-desactivar/", views.DepartmentToggleView.as_view(), name="department_toggle"),
    path("cargos/", views.PositionListView.as_view(), name="position_list"),
    path("cargos/<int:pk>/activar-desactivar/", views.PositionToggleView.as_view(), name="position_toggle"),
    # Horarios
    path("horarios/", views.WorkScheduleListView.as_view(), name="work_schedule_list"),
    # Tipos de ausencia
    path("tipos-ausencia/", views.LeaveTypeListView.as_view(), name="leave_type_list"),
    path("tipos-ausencia/sugeridos/", views.LeaveTypeSeedDefaultsView.as_view(), name="leave_type_seed_defaults"),
]
