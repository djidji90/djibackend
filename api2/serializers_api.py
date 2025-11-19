# api2/serializers_api.py
from rest_framework import serializers
from typing import List, Dict, Any

class SongSuggestionSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    artist = serializers.CharField()
    genre = serializers.CharField()
    type = serializers.CharField()
    display = serializers.CharField()

class SuggestionsResponseSerializer(serializers.Serializer):
    suggestions = SongSuggestionSerializer(many=True)

class LikesResponseSerializer(serializers.Serializer):
    song_id = serializers.IntegerField()
    likes_count = serializers.IntegerField()
    title = serializers.CharField()

class LikeActionSerializer(serializers.Serializer):
    message = serializers.CharField()
    likes_count = serializers.IntegerField()
    song_id = serializers.IntegerField()

class DownloadResponseSerializer(serializers.Serializer):
    download_url = serializers.URLField()

class StreamResponseSerializer(serializers.Serializer):
    stream_url = serializers.URLField()
    song_title = serializers.CharField()
    artist = serializers.CharField()
    duration = serializers.CharField(required=False, allow_null=True)

class ArtistsResponseSerializer(serializers.Serializer):
    artists = serializers.ListField(child=serializers.CharField())

class RandomSongsResponseSerializer(serializers.Serializer):
    random_songs = serializers.ListField(child=serializers.DictField())

class UploadResponseSerializer(serializers.Serializer):
    song_id = serializers.IntegerField()
    file_upload_url = serializers.URLField()
    image_upload_url = serializers.URLField(required=False, allow_null=True)
    message = serializers.CharField()

class StatsResponseSerializer(serializers.Serializer):
    total_songs = serializers.IntegerField()
    total_plays = serializers.IntegerField()
    total_downloads = serializers.IntegerField()
    total_users = serializers.IntegerField()
    popular_genres = serializers.ListField(child=serializers.DictField())