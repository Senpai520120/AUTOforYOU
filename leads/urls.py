from django.urls import path

from .views import LeadCreateView, MyLeadsView

app_name = 'leads'

urlpatterns = [
    path('', LeadCreateView.as_view(), name='lead-create'),
    path('mine/', MyLeadsView.as_view(), name='lead-mine'),
]
