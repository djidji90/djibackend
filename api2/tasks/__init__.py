# api2/tasks/__init__.py
from .upload_tasks import process_direct_upload, cleanup_expired_uploads, cleanup_orphaned_r2_files, reprocess_failed_upload
#from .audio_tasks import generate_audio_preview
#from .search_tasks import index_song, remove_song_from_index, reindex_all_songs
#from .notification_tasks import notify_upload_complete, notify_new_follower, notify_new_comment, send_welcome_email
#from .ml_tasks import analyze_audio_features, generate_recommendations, update_user_taste_profile

__all__ = [
    'process_direct_upload',
    'cleanup_expired_uploads',
    'cleanup_orphaned_r2_files',
    'reprocess_failed_upload',
    'generate_audio_preview',
    'index_song',
    'remove_song_from_index',
    'reindex_all_songs',
    'notify_upload_complete',
    'notify_new_follower',
    'notify_new_comment',
    'send_welcome_email',
    'analyze_audio_features',
    'generate_recommendations',
    'update_user_taste_profile'
]
