from rest_framework import serializers
from .models import Song, Like, Download, Comment, CommentReaction, MusicEvent


class SongSerializer(serializers.ModelSerializer):
    likes_count = serializers.IntegerField(read_only=True)  # Se puede calcular dinámicamente si es necesario
    comments_count = serializers.IntegerField(source='comments.count', read_only=True)
    comments = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()

    class Meta:
        model = Song
        fields = ['id', 'title', 'artist', 'genre', 'file', 'image', 'likes_count', 'comments_count', 'comments', 'created_at']

    def get_comments(self, obj):
        comments = obj.comments.all()[:5]  # Solo los 5 comentarios más recientes
        return CommentSerializer(comments, many=True).data

    def get_image(self, obj):
        request = self.context.get('request')
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        return None


class LikeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Like
        fields = ['user', 'song', 'created_at']


class DownloadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Download
        fields = ['user', 'song', 'downloaded_at']


class CommentSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField(read_only=True)
    is_user_comment = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = ['id', 'song', 'user', 'content', 'created_at', 'is_user_comment']

    def get_is_user_comment(self, obj):
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            return obj.user == request.user
        return False


class CommentReactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommentReaction
        fields = ['id', 'comment', 'user', 'created_at']


class MusicEventSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    class Meta:
        model = MusicEvent
        fields = ['id', 'title', 'description', 'event_date', 'location', 'image', 'is_active', 'created_at']

    def get_image(self, obj):
        request = self.context.get('request')
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        return None