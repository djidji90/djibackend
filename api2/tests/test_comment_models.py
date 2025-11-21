# api2/tests/test_comment_models.py
from django.test import TestCase
from api2.models import Song, Comment
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

User = get_user_model()

class TestCommentModel(TestCase):
    def setUp(self):
        """Configuración inicial para todas las pruebas"""
        self.user = User.objects.create_user(
            username='commentuser',
            email='comment@example.com',
            password='testpass123'
        )
        self.song = Song.objects.create(
            title="Comment Test Song",
            artist="Comment Test Artist",
            genre="Rock",
            uploaded_by=self.user
        )
        print("✅ Configuración de CommentModel completada")
    
    def test_comment_creation(self):
        """Test creación de comentario"""
        print("💬 Probando creación de comentario...")
        comment = Comment.objects.create(
            user=self.user,
            song=self.song,
            content="Este es un comentario de prueba"
        )
        
        self.assertEqual(comment.user, self.user)
        self.assertEqual(comment.song, self.song)
        self.assertEqual(comment.content, "Este es un comentario de prueba")
        self.assertFalse(comment.is_edited)
        self.assertIsNotNone(comment.created_at)
        print("✅ Test de creación de comentario pasado")
    
    def test_comment_clean_validation_empty(self):
        """Test validación de comentario vacío"""
        print("💬 Probando validación de comentario vacío...")
        comment = Comment(
            user=self.user,
            song=self.song,
            content="   "  # Solo espacios
        )
        
        with self.assertRaises(ValidationError):
            comment.clean()
        print("✅ Test de validación de comentario vacío pasado")
    
    def test_comment_edit_flag(self):
        """Test que editar comentario marca is_edited"""
        print("💬 Probando flag de edición...")
        comment = Comment.objects.create(
            user=self.user,
            song=self.song,
            content="Contenido original"
        )
        
        # Primera edición
        comment.content = "Contenido editado"
        comment.save()
        
        self.assertTrue(comment.is_edited)
        print("✅ Test de flag de edición pasado")
    
    def test_comment_str_representation(self):
        """Test representación en string"""
        print("💬 Probando representación string...")
        comment = Comment.objects.create(
            user=self.user,
            song=self.song,
            content="Mi comentario"
        )
        
        expected_str = f"{self.user.username} - {self.song.title}"
        self.assertEqual(str(comment), expected_str)
        print("✅ Test de representación string pasado")