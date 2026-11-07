from django.urls import path

from .views import (
    BrokerLeadDetailView,
    BrokerLeadListView,
    BrokerLeadPartnerStatusView,
    BrokerLeadQualificationView,
    BrokerLeadStatusView,
    BrokerLeadTakeView,
    LeadExportView,
)

app_name = 'broker'

urlpatterns = [
    path('leads/', BrokerLeadListView.as_view(), name='lead-list'),
    path('leads/export.csv', LeadExportView.as_view(), name='lead-export'),
    path('leads/<int:pk>/', BrokerLeadDetailView.as_view(), name='lead-detail'),
    path('leads/<int:pk>/status/', BrokerLeadStatusView.as_view(), name='lead-status'),
    path('leads/<int:pk>/take/', BrokerLeadTakeView.as_view(), name='lead-take'),
    path('leads/<int:pk>/qualification/', BrokerLeadQualificationView.as_view(), name='lead-qualification'),
    path('leads/<int:pk>/partner-status/', BrokerLeadPartnerStatusView.as_view(), name='lead-partner-status'),
]
