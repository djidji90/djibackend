# tests/factories.py
import factory
from django.contrib.auth.models import User
from api2.models import Song, Like, Download, Comment, MusicEvent, UserProfile, PlayHistory
from faker import Faker

fake = Faker()

class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
    
    username = factory.Sequence(lambda n: f'testuser{n}')
    email = factory.LazyAttribute(lambda obj: f'{obj.username}@example.com')
    password = factory.PostGenerationMethodCall('set_password', 'testpass123')

class SongFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Song
    
    title = factory.LazyFunction(lambda: fake.catch_phrase())
    artist = factory.LazyFunction(lambda: fake.name())
    genre = factory.LazyFunction(lambda: fake.random_element(['Rock', 'Pop', 'Jazz', 'Hip Hop', 'Electronic']))
    duration = factory.LazyFunction(lambda: f"{fake.random_int(2, 5)}:{fake.random_int(10, 59):02d}")
    file_key = factory.Sequence(lambda n: f"songs/test_song_{n}.mp3")
    image_key = factory.Sequence(lambda n: f"images/test_image_{n}.jpg")
    uploaded_by = factory.SubFactory(UserFactory)
    is_public = True
    likes_count = 0
    plays_count = 0
    downloads_count = 0

class MusicEventFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = MusicEvent
    
    title = factory.LazyFunction(lambda: fake.sentence())
    description = factory.LazyFunction(lambda: fake.paragraph())
    event_type = factory.LazyFunction(lambda: fake.random_element(['concert', 'festival', 'party', 'workshop']))
    event_date = factory.LazyFunction(lambda: fake.future_datetime(end_date="+30d"))
    location = factory.LazyFunction(lambda: fake.city())
    venue = factory.LazyFunction(lambda: fake.company())
    image_key = factory.Sequence(lambda n: f"events/test_event_{n}.jpg")
    ticket_url = factory.LazyFunction(lambda: fake.url())
    price = factory.LazyFunction(lambda: fake.random_number(digits=2))
    is_active = True
    is_featured = False

class UserProfileFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = UserProfile
    
    user = factory.SubFactory(UserFactory)
    bio = factory.LazyFunction(lambda: fake.paragraph())
    avatar_key = factory.Sequence(lambda n: f"avatars/test_avatar_{n}.jpg")
    website = factory.LazyFunction(lambda: fake.url())
    location = factory.LazyFunction(lambda: fake.city())
    favorite_genres = factory.LazyFunction(lambda: ['Rock', 'Pop'])
    notifications_enabled = True
    songs_uploaded = 0
    total_listening_time = 0

class LikeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Like
    
    user = factory.SubFactory(UserFactory)
    song = factory.SubFactory(SongFactory)

class DownloadFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Download
    
    user = factory.SubFactory(UserFactory)
    song = factory.SubFactory(SongFactory)
    ip_address = factory.LazyFunction(lambda: fake.ipv4())

class CommentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Comment
    
    user = factory.SubFactory(UserFactory)
    song = factory.SubFactory(SongFactory)
    content = factory.LazyFunction(lambda: fake.paragraph())

class PlayHistoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PlayHistory
    
    user = factory.SubFactory(UserFactory)
    song = factory.SubFactory(SongFactory)
    duration_played = factory.LazyFunction(lambda: fake.random_int(10, 300))
    ip_address = factory.LazyFunction(lambda: fake.ipv4())