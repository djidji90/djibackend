 # api2/tests/test_musicevent_models.py
from django.test import TestCase
from api2.models import MusicEvent
from django.utils import timezone
from datetime import timedelta

class TestMusicEventModel(TestCase):
    def setUp(self):
        """Configuración inicial para todas las pruebas"""
        print("✅ Configuración de MusicEventModel completada")
    
    def test_music_event_creation(self):
        """Test creación de evento musical"""
        print("🎪 Probando creación de evento musical...")
        event = MusicEvent.objects.create(
            title="Concierto de Prueba",
            description="Este es un evento de prueba",
            event_type="concert",
            event_date=timezone.now() + timedelta(days=10),
            location="Madrid, España",
            venue="Estadio Wanda",
            ticket_url="https://example.com/tickets",
            price=50.00,
            is_active=True,
            is_featured=False
        )
        
        self.assertEqual(event.title, "Concierto de Prueba")
        self.assertEqual(event.event_type, "concert")
        self.assertEqual(event.location, "Madrid, España")
        self.assertEqual(event.price, 50.00)
        self.assertTrue(event.is_active)
        self.assertFalse(event.is_featured)
        print("✅ Test de creación de evento musical pasado")
    
    def test_music_event_str_representation(self):
        """Test representación en string"""
        print("🎪 Probando representación string...")
        event_date = timezone.now() + timedelta(days=5)
        event = MusicEvent.objects.create(
            title="Festival de Verano",
            description="Gran festival",
            event_type="festival",
            event_date=event_date,
            location="Barcelona"
        )
        
        self.assertEqual(str(event), "Festival de Verano")
        print("✅ Test de representación string pasado")
    
    def test_is_upcoming_property(self):
        """Test propiedad is_upcoming"""
        print("🎪 Probando propiedad is_upcoming...")
        
        # Evento futuro
        future_event = MusicEvent.objects.create(
            title="Evento Futuro",
            description="Evento que viene",
            event_type="concert",
            event_date=timezone.now() + timedelta(days=1),
            location="Test"
        )
        
        # Evento pasado
        past_event = MusicEvent.objects.create(
            title="Evento Pasado",
            description="Evento que ya pasó",
            event_type="concert",
            event_date=timezone.now() - timedelta(days=1),
            location="Test"
        )
        
        self.assertTrue(future_event.is_upcoming)
        self.assertFalse(past_event.is_upcoming)
        print("✅ Test de propiedad is_upcoming pasado")
    
    def test_days_until_event_property(self):
        """Test propiedad days_until_event"""
        print("🎪 Probando propiedad days_until_event...")
        event_date = timezone.now() + timedelta(days=7, hours=5)  # 7 días y 5 horas
        event = MusicEvent.objects.create(
            title="Evento en 7 días",
            description="Evento próximo",
            event_type="concert",
            event_date=event_date,
            location="Test"
        )
        
        # Debería devolver 7 días (ignora las horas)
        self.assertEqual(event.days_until_event, 7)
        print("✅ Test de propiedad days_until_event pasado")