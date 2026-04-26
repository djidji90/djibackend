# wallet/urls.py
"""
URLs para las APIs del wallet.
"""
from django.urls import path
from . import views
from .health import WalletHealthCheckView  # ✅ IMPORTAR DESDE health.py

urlpatterns = [
    # ============================================
    # BALANCE Y TRANSACCIONES
    # ============================================
    path('balance/', views.WalletBalanceView.as_view(), name='wallet-balance'),
    path('transactions/', views.TransactionHistoryView.as_view(), name='transaction-list'),
    path('transactions/<str:reference>/', views.TransactionDetailView.as_view(), name='transaction-detail'),
    path('health/', WalletHealthCheckView.as_view(), name='wallet-health'),
    
    # ============================================
    # COMPRAS
    # ============================================
    path('songs/<int:song_id>/purchase/', views.PurchaseSongView.as_view(), name='purchase-song'),
    path('purchases/', views.UserPurchasesView.as_view(), name='user-purchases'),
    
    # ============================================
    # RECARGAS
    # ============================================
    path('deposit/', views.UserDepositView.as_view(), name='wallet-deposit'),
    path('redeem/', views.RedeemCodeView.as_view(), name='redeem-code'),
    
    # ============================================
    # ARTISTAS
    # ============================================
    path('artist/earnings/', views.ArtistEarningsView.as_view(), name='artist-earnings'),
    path('artist/holds/', views.ArtistHoldsView.as_view(), name='artist-holds'),
    
    # ===============================   =============
    # ADMIN (HOLDS)
    # ============================================
    path('admin/holds/release/', views.ReleaseHoldView.as_view(), name='release-hold'),
    
    # ============================================
    # CÓDIGOS DE RECARGA
    # ============================================
    path('codes/', views.DepositCodeListView.as_view(), name='code-list'),
    path('codes/<int:pk>/', views.DepositCodeDetailView.as_view(), name='code-detail'),
]

# ============================================================================
# URLS PARA SISTEMA DE AGENTES (NUEVAS)
# ============================================================================

agent_urlpatterns = [
    # Dashboard y operaciones de agente
    path('agent/dashboard/', views.AgentDashboardView.as_view(), name='agent-dashboard'),
    path('agent/deposit/', views.AgentDepositView.as_view(), name='agent-deposit'),
    path('agent/generate-code/', views.AgentGenerateCodeView.as_view(), name='agent-generate-code'),
    path('agent/codes/', views.AgentCodesView.as_view(), name='agent-codes'),
    path('agent/search/', views.AgentSearchUserView.as_view(), name='agent-search'),
    path('agent/earnings/', views.AgentEarningsView.as_view(), name='agent-earnings'),
    
    # Ubicaciones
    path('locations/', views.LocationsListView.as_view(), name='locations'),
    
    # Códigos de recarga (QR y canje)
    path('codes/<str:code>/qr/', views.CodeQRView.as_view(), name='code-qr'),
]

# ============================================================================
# URLS DE ADMINISTRACIÓN DE AGENTES
# ============================================================================

admin_agent_urlpatterns = [
    path('admin/agents/', views.AgentsListView.as_view(), name='admin-agents'),
    path('admin/agents/create/', views.AgentCreateView.as_view(), name='admin-agent-create'),
]

# wallet/urls.py - AGREGAR AL FINAL

# wallet/urls.py - AGREGAR AL FINAL

# ============================================================================
# URLS PARA SISTEMA DE OFICINA (RETIROS)
# ============================================================================

office_urlpatterns = [
    # Búsqueda de artistas
    path('office/search/', views.OfficeSearchArtistView.as_view(), name='office-search'),
    
    # Procesar retiro
    path('office/withdraw/', views.OfficeProcessWithdrawalView.as_view(), name='office-withdraw'),
    
    # Historial de retiros
    path('office/withdrawals/', views.OfficeWithdrawalHistoryView.as_view(), name='office-withdrawals'),
    
    # Detalle de retiro específico
    path('office/withdrawals/<int:withdrawal_id>/', views.OfficeWithdrawalDetailView.as_view(), name='office-withdrawal-detail'),
    
    # Reversar retiro (solo admin)
    path('admin/office/reverse/<int:withdrawal_id>/', views.OfficeReverseWithdrawalView.as_view(), name='office-reverse-withdrawal'),
]

# ============================================================================
# COMBINAR TODAS LAS URLS (actualizar)
# ============================================================================

urlpatterns += agent_urlpatterns + admin_agent_urlpatterns + office_urlpatterns
# ============================================================================
# COMBINAR TODAS LAS URLS (actualizar)
# ============================================================================
# ============================================================================
# COMBINAR TODAS LAS URLS
# ============================================================================