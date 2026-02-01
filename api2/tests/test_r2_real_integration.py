# 添加这些导入语句到 test_r2_real_integration.py 文件的顶部
import os

from django.test import tag
import pytest
from unittest import TestCase, SkipTest  # 或者使用 unittest.skip
import pytest



@tag('integration', 'requires_r2')
class RealR2IntegrationTests(TestCase):
    """Tests que requieren R2 real"""
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Verificar que R2 está configurado
        if not all([os.getenv('R2_ACCESS_KEY_ID'), os.getenv('R2_BUCKET_NAME')]):
            raise SkipTest("R2 no configurado para tests reales")   