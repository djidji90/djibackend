# wallet/load_tests/test_scenarios.py
"""
Escenarios de prueba específicos
"""
import requests
import concurrent.futures
import time
from decimal import Decimal


class LoadTestScenarios:
    """Escenarios de prueba para alta concurrencia"""
    
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
        self.results = []
    
    def test_concurrent_deposits(self, user_id, amount, num_requests=10):
        """Escenario 1: Depósitos concurrentes"""
        def make_deposit(attempt):
            headers = {'X-Idempotency-Key': f"deposit-{user_id}-{attempt}-{int(time.time())}"}
            response = requests.post(
                f"{self.base_url}/api/wallet/deposit/",
                json={'amount': float(amount)},
                headers=headers
            )
            return {
                'attempt': attempt,
                'status': response.status_code,
                'success': response.status_code in [200, 201]
            }
        
        start = time.time()
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_requests) as executor:
            futures = [executor.submit(make_deposit, i) for i in range(num_requests)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        
        duration = time.time() - start
        
        successful = sum(1 for r in results if r['success'])
        
        return {
            'scenario': 'Concurrent Deposits',
            'num_requests': num_requests,
            'successful': successful,
            'failed': num_requests - successful,
            'duration': f"{duration:.2f}s",
            'throughput': f"{num_requests/duration:.2f} req/s"
        }
    
    def test_concurrent_withdrawals(self, artist_id, amount, num_requests=5):
        """Escenario 2: Retiros concurrentes"""
        def make_withdrawal(attempt):
            headers = {
                'X-Idempotency-Key': f"withdrawal-{artist_id}-{attempt}-{int(time.time())}"
            }
            response = requests.post(
                f"{self.base_url}/api/wallet/office/withdraw/",
                json={
                    'artist_id': artist_id,
                    'amount': float(amount),
                    'withdrawal_method': 'cash',
                    'id_number': '12345678'
                },
                headers=headers
            )
            return {
                'attempt': attempt,
                'status': response.status_code,
                'success': response.status_code == 201
            }
        
        start = time.time()
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_requests) as executor:
            futures = [executor.submit(make_withdrawal, i) for i in range(num_requests)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        
        duration = time.time() - start
        
        successful = sum(1 for r in results if r['success'])
        
        return {
            'scenario': 'Concurrent Withdrawals',
            'num_requests': num_requests,
            'successful': successful,
            'failed': num_requests - successful,
            'duration': f"{duration:.2f}s"
        }
    
    def test_balance_reads(self, user_id, num_requests=100):
        """Escenario 3: Lecturas concurrentes de balance"""
        def get_balance():
            response = requests.get(f"{self.base_url}/api/wallet/balance/")
            return response.status_code == 200
        
        start = time.time()
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_requests) as executor:
            futures = [executor.submit(get_balance) for _ in range(num_requests)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        
        duration = time.time() - start
        successful = sum(results)
        
        return {
            'scenario': 'Balance Reads',
            'num_requests': num_requests,
            'successful': successful,
            'failed': num_requests - successful,
            'duration': f"{duration:.2f}s",
            'throughput': f"{num_requests/duration:.2f} req/s"
        }
    
    def run_all(self):
        """Ejecutar todos los escenarios"""
        print("\n" + "="*70)
        print("🧪 INICIANDO PRUEBAS DE CARGA")
        print("="*70)
        
        # Escenario 1: Lecturas masivas
        result1 = self.test_balance_reads(1, 100)
        print(f"\n✅ {result1['scenario']}")
        print(f"   Requests: {result1['num_requests']}")
        print(f"   Éxitos: {result1['successful']}")
        print(f"   Fallos: {result1['failed']}")
        print(f"   Throughput: {result1['throughput']}")
        
        # Escenario 2: Depósitos concurrentes
        result2 = self.test_concurrent_deposits(1, 1000, 20)
        print(f"\n✅ {result2['scenario']}")
        print(f"   Requests: {result2['num_requests']}")
        print(f"   Éxitos: {result2['successful']}")
        print(f"   Fallos: {result2['failed']}")
        print(f"   Duración: {result2['duration']}")
        
        print("\n" + "="*70)
        print("📊 RESULTADOS DE PRUEBAS DE CARGA")
        print("="*70)
        
        return [result1, result2]


# Ejecutar pruebas
if __name__ == "__main__":
    tester = LoadTestScenarios()
    results = tester.run_all()