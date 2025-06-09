# utilidades/admin.py

from django.contrib import admin
from .models import SearchHistory, BulkCheck, Report

@admin.register(SearchHistory)
class SearchHistoryAdmin(admin.ModelAdmin):
    list_display  = ['user', 'category', 'timestamp', 'items_count', 'result_count']
    list_filter   = ['category', 'timestamp', 'user']
    search_fields = ['user__username', 'params']

# Si aún no están registrados, puedes dejar también:
@admin.register(BulkCheck)
class BulkCheckAdmin(admin.ModelAdmin):
    list_display = ['user', 'check_type', 'timestamp']

@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ['user', 'report_type', 'created']
