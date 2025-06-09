# dashboard/views.py

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum
from django.contrib.auth import get_user_model
import json

from utilidades.models import SearchHistory

@login_required
def panel(request):
    """
    Dashboard con métricas de búsquedas y reconocimientos.
    """
    # Total usuarios
    User = get_user_model()
    total_users = User.objects.count()

    # Conteo búsquedas por tipo para la gráfica
    qs_counts = (
        SearchHistory.objects
        .filter(user=request.user)
        .values('category')
        .annotate(count=Count('id'))
    )
    # Convertir a listas paralelas
    categories = [item['category'] for item in qs_counts]
    counts     = [item['count']    for item in qs_counts]

    # Métricas agregadas
    total_faces = (
        SearchHistory.objects
        .filter(user=request.user, category__startswith='face')
        .aggregate(sum=Sum('result_count'))['sum'] or 0
    )
    total_videos = (
        SearchHistory.objects
        .filter(user=request.user, category__endswith='video')
        .aggregate(sum=Sum('items_count'))['sum'] or 0
    )
    total_images = (
        SearchHistory.objects
        .filter(user=request.user, category__endswith='image')
        .aggregate(sum=Sum('items_count'))['sum'] or 0
    )

    context = {
    'total_users': total_users,
    'total_faces': total_faces,
    'total_videos': total_videos,
    'total_images': total_images,
    'categories_json': json.dumps(categories),
    'counts_json':     json.dumps(counts),
    
    }
    return render(request, 'dashboard/panel.html', context)
