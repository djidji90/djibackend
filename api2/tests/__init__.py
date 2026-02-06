"""
Tests para el sistema de upload R2
"""

# Importar todos los tests
from .test_r2_upload_final import (
    R2UploadFinalTest,
    R2UploadEdgeCasesTest,
    run_comprehensive_test_suite
)

# Tests de sistema
from .test_system_ready import SystemReadyTests

# Tests específicos
from .test_upload_final_fixed import TestDirectUploadFinalFixed

__all__ = [
    'R2UploadFinalTest',
    'R2UploadEdgeCasesTest',
    'SystemReadyTests',
    'TestDirectUploadFinalFixed',
    'run_comprehensive_test_suite',
]