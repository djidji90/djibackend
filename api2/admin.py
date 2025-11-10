from django.contrib import admin
from .models import Song, Like, Download, Comment, CommentReaction, MusicEvent


@admin.register(Song)
class SongAdmin(admin.ModelAdmin):
    list_display = ('title', 'artist', 'genre', 'likes_count', 'created_at')
    search_fields = ('title', 'artist', 'genre')
    list_filter = ('genre', 'created_at')
    ordering = ('-created_at',)
    readonly_fields = ('likes_count',)


@admin.register(Like)
class LikeAdmin(admin.ModelAdmin):
    list_display = ('user', 'song', 'created_at')
    search_fields = ('user__username', 'song__title')
    list_filter = ('created_at',)


@admin.register(Download)
class DownloadAdmin(admin.ModelAdmin):
    list_display = ('user', 'song', 'downloaded_at')
    search_fields = ('user__username', 'song__title')
    list_filter = ('downloaded_at',)


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('user', 'song', 'content', 'created_at')
    search_fields = ('user__username', 'song__title', 'content')
    list_filter = ('created_at',)
    ordering = ('-created_at',)


@admin.register(CommentReaction)
class CommentReactionAdmin(admin.ModelAdmin):
    list_display = ('user', 'comment', 'created_at')
    search_fields = ('user__username', 'comment__content')
    list_filter = ('created_at',)


@admin.register(MusicEvent)
class MusicEventAdmin(admin.ModelAdmin):
    list_display = ('title', 'event_date', 'location', 'is_active', 'created_at')
    search_fields = ('title', 'description', 'location')
    list_filter = ('event_date', 'is_active', 'created_at')
    ordering = ('-event_date',)
    readonly_fields = ('is_active', 'created_at')







