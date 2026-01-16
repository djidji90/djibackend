import time
from django.http import JsonResponse

class TimeoutMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Timeout de 4 minutos para uploads
        start_time = time.time()
        timeout = 240  # 4 minutos
        
        try:
            response = self.get_response(request)
            elapsed = time.time() - start_time
            
            if elapsed > 60:  # Log si tarda más de 1 minuto
                print(f"⏱️ Request lento: {request.path} - {elapsed:.1f}s")
            
            return response
            
        except Exception as e:
            elapsed = time.time() - start_time
            if elapsed > timeout:
                return JsonResponse({
                    "error": "timeout",
                    "message": "La operación tardó demasiado tiempo"
                }, status=504)
            raise 