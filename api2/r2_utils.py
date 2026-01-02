// src/components/music/MusicPlayer.jsx
import React, { useState, useEffect } from 'react';
import {
  Box,
  Paper,
  Slider,
  IconButton,
  Typography,
  LinearProgress,
  Tooltip,
  Chip,
  Menu,
  MenuItem,
  Dialog,
  DialogContent,
  DialogActions,
  Button
} from '@mui/material';
import {
  PlayArrow,
  Pause,
  SkipPrevious,
  SkipNext,
  VolumeUp,
  VolumeOff,
  VolumeDown,
  Favorite,
  FavoriteBorder,
  PlaylistPlay,
  Repeat,
  RepeatOne,
  Shuffle,
  Download,
  MoreVert,
  Close
} from '@mui/icons-material';
import { useAudioPlayer } from '../../hooks/useAudioPlayer';
import ApiIntegrator from '../../services/ApiIntegrator';

const MusicPlayer = () => {
  const {
    // Estado
    currentSong,
    isPlaying,
    volume,
    progress,
    duration,
    isMuted,
    loop,
    shuffle,
    playlist,
    currentIndex,
    error,
    isBuffering,
    
    // Métodos
    playSong,
    togglePlay,
    seek,
    setVolume,
    toggleMute,
    toggleLoop,
    toggleShuffle,
    playNext,
    playPrev,
    createPlaylist,
    stop,
    formatTime,
    clearError
  } = useAudioPlayer();

  const [volumeOpen, setVolumeOpen] = useState(false);
  const [moreMenuAnchor, setMoreMenuAnchor] = useState(null);
  const [liked, setLiked] = useState(false);
  const [showPlaylist, setShowPlaylist] = useState(false);
  const [loadingLike, setLoadingLike] = useState(false);

  // Verificar si la canción actual tiene like
  useEffect(() => {
    if (currentSong?.id) {
      // Aquí podrías hacer una llamada para verificar si el usuario actual dio like
      setLiked(false); // Temporal
    }
  }, [currentSong]);

  // Manejar like
  const handleLike = async () => {
    if (!currentSong?.id || loadingLike) return;

    setLoadingLike(true);
    try {
      if (liked) {
        // Aquí necesitarías un endpoint para quitar like
        // await ApiIntegrator.songs.unlike(currentSong.id);
      } else {
        await ApiIntegrator.songs.like(currentSong.id);
      }
      setLiked(!liked);
    } catch (error) {
      console.error('Error al dar like:', error);
    } finally {
      setLoadingLike(false);
    }
  };

  // Manejar descarga
  const handleDownload = async () => {
    if (!currentSong?.id) return;

    try {
      const response = await ApiIntegrator.songs.download(currentSong.id);
      if (response.data?.url) {
        window.open(response.data.url, '_blank');
      }
    } catch (error) {
      console.error('Error al descargar:', error);
    }
  };

  // Crear playlist desde canciones de la API
  const loadPlaylist = async () => {
    try {
      const response = await ApiIntegrator.songs.getAll();
      const songs = response.data.results || response.data;
      
      if (songs.length > 0) {
        createPlaylist(songs, 0);
      }
    } catch (error) {
      console.error('Error cargando playlist:', error);
    }
  };

  // Inicializar con playlist
  useEffect(() => {
    if (playlist.length === 0) {
      loadPlaylist();
    }
  }, []);

  // Mostrar errores
  useEffect(() => {
    if (error) {
      console.error('Player error:', error);
      // Podrías mostrar un toast aquí
    }
  }, [error]);

  // Cerrar menú more
  const handleMoreMenuClose = () => {
    setMoreMenuAnchor(null);
  };

  if (!currentSong && playlist.length === 0) {
    return (
      <Paper 
        elevation={3} 
        sx={{ 
          p: 2, 
          borderRadius: 2,
          bgcolor: 'background.paper',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center'
        }}
      >
        <Typography color="text.secondary">
          Selecciona una canción para reproducir
        </Typography>
      </Paper>
    );
  }

  return (
    <>
      {/* Player principal */}
      <Paper 
        elevation={3} 
        sx={{ 
          p: 2, 
          borderRadius: 2,
          bgcolor: 'background.paper',
          position: 'relative',
          overflow: 'hidden'
        }}
      >
        {/* Loading indicator */}
        {isBuffering && (
          <LinearProgress 
            sx={{ 
              position: 'absolute', 
              top: 0, 
              left: 0, 
              right: 0 
            }} 
          />
        )}

        {/* Contenido del player */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          {/* Cover y info */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, flex: 1 }}>
            {/* Cover */}
            <Box
              sx={{
                width: 60,
                height: 60,
                borderRadius: 1,
                bgcolor: 'grey.300',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                overflow: 'hidden',
                flexShrink: 0
              }}
            >
              {currentSong?.image ? (
                <img 
                  src={currentSong.image} 
                  alt={currentSong.title}
                  style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                />
              ) : (
                <Typography variant="h4" color="text.secondary">
                  🎵
                </Typography>
              )}
            </Box>

            {/* Info */}
            <Box sx={{ minWidth: 0, flex: 1 }}>
              <Typography variant="subtitle1" noWrap fontWeight="medium">
                {currentSong?.title || 'Sin título'}
              </Typography>
              <Typography variant="body2" color="text.secondary" noWrap>
                {currentSong?.artist || 'Artista desconocido'}
              </Typography>
              {currentSong?.genre && (
                <Chip 
                  label={currentSong.genre} 
                  size="small" 
                  sx={{ mt: 0.5, height: 20 }}
                />
              )}
            </Box>
          </Box>

          {/* Controles principales */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            {/* Shuffle */}
            <Tooltip title="Aleatorio">
              <IconButton 
                size="small" 
                onClick={toggleShuffle}
                color={shuffle ? "primary" : "default"}
              >
                <Shuffle fontSize="small" />
              </IconButton>
            </Tooltip>

            {/* Anterior */}
            <Tooltip title="Anterior">
              <IconButton 
                size="small" 
                onClick={playPrev}
                disabled={playlist.length <= 1}
              >
                <SkipPrevious />
              </IconButton>
            </Tooltip>

            {/* Play/Pause */}
            <IconButton 
              onClick={togglePlay}
              sx={{ 
                bgcolor: 'primary.main',
                color: 'primary.contrastText',
                '&:hover': { bgcolor: 'primary.dark' }
              }}
              disabled={isBuffering}
            >
              {isPlaying ? <Pause /> : <PlayArrow />}
            </IconButton>

            {/* Siguiente */}
            <Tooltip title="Siguiente">
              <IconButton 
                size="small" 
                onClick={playNext}
                disabled={playlist.length <= 1}
              >
                <SkipNext />
              </IconButton>
            </Tooltip>

            {/* Loop */}
            <Tooltip title={loop ? "Repetir una" : "Repetir todas"}>
              <IconButton 
                size="small" 
                onClick={toggleLoop}
                color={loop ? "primary" : "default"}
              >
                {loop ? <RepeatOne fontSize="small" /> : <Repeat fontSize="small" />}
              </IconButton>
            </Tooltip>
          </Box>

          {/* Controles secundarios */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            {/* Like */}
            <Tooltip title={liked ? "Quitar like" : "Dar like"}>
              <IconButton 
                size="small" 
                onClick={handleLike}
                disabled={loadingLike}
                color={liked ? "error" : "default"}
              >
                {liked ? <Favorite /> : <FavoriteBorder />}
              </IconButton>
            </Tooltip>

            {/* Volume */}
            <Box 
              sx={{ 
                position: 'relative',
                display: 'flex',
                alignItems: 'center'
              }}
              onMouseEnter={() => setVolumeOpen(true)}
              onMouseLeave={() => setVolumeOpen(false)}
            >
              <Tooltip title={isMuted ? "Activar sonido" : "Silenciar"}>
                <IconButton 
                  size="small" 
                  onClick={toggleMute}
                >
                  {isMuted ? <VolumeOff /> : volume > 0.5 ? <VolumeUp /> : <VolumeDown />}
                </IconButton>
              </Tooltip>

              {/* Slider de volumen */}
              {volumeOpen && (
                <Box
                  sx={{
                    position: 'absolute',
                    bottom: '100%',
                    left: '50%',
                    transform: 'translateX(-50%)',
                    bgcolor: 'background.paper',
                    p: 1,
                    borderRadius: 1,
                    boxShadow: 3,
                    zIndex: 1
                  }}
                >
                  <Slider
                    orientation="vertical"
                    value={isMuted ? 0 : volume * 100}
                    onChange={(e, value) => setVolume(value / 100)}
                    min={0}
                    max={100}
                    sx={{ height: 100 }}
                  />
                </Box>
              )}
            </Box>

            {/* Más opciones */}
            <Tooltip title="Más opciones">
              <IconButton 
                size="small" 
                onClick={(e) => setMoreMenuAnchor(e.currentTarget)}
              >
                <MoreVert />
              </IconButton>
            </Tooltip>
          </Box>
        </Box>

        {/* Barra de progreso */}
        <Box sx={{ mt: 2 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
            <Typography variant="caption" color="text.secondary">
              {formatTime((progress / 100) * duration)}
            </Typography>
            <Slider
              value={progress}
              onChange={(e, value) => seek(value)}
              sx={{ flex: 1 }}
            />
            <Typography variant="caption" color="text.secondary">
              {formatTime(duration)}
            </Typography>
          </Box>
        </Box>
      </Paper>

      {/* Menú de más opciones */}
      <Menu
        anchorEl={moreMenuAnchor}
        open={Boolean(moreMenuAnchor)}
        onClose={handleMoreMenuClose}
      >
        <MenuItem onClick={() => {
          handleDownload();
          handleMoreMenuClose();
        }}>
          <Download fontSize="small" sx={{ mr: 1 }} />
          Descargar
        </MenuItem>
        <MenuItem onClick={() => {
          setShowPlaylist(true);
          handleMoreMenuClose();
        }}>
          <PlaylistPlay fontSize="small" sx={{ mr: 1 }} />
          Ver playlist ({playlist.length})
        </MenuItem>
        <MenuItem onClick={() => {
          stop();
          handleMoreMenuClose();
        }}>
          <Close fontSize="small" sx={{ mr: 1 }} />
          Detener
        </MenuItem>
      </Menu>

      {/* Dialog de playlist */}
      <Dialog 
        open={showPlaylist} 
        onClose={() => setShowPlaylist(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogContent>
          <Typography variant="h6" gutterBottom>
            Playlist ({playlist.length})
          </Typography>
          
          <Box sx={{ maxHeight: 400, overflow: 'auto' }}>
            {playlist.map((song, index) => (
              <Box
                key={song.id}
                sx={{
                  p: 1.5,
                  borderRadius: 1,
                  bgcolor: index === currentIndex ? 'action.selected' : 'transparent',
                  cursor: 'pointer',
                  '&:hover': { bgcolor: 'action.hover' },
                  mb: 0.5
                }}
                onClick={() => {
                  createPlaylist(playlist, index);
                  setShowPlaylist(false);
                }}
              >
                <Typography variant="body1">
                  {index + 1}. {song.title}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {song.artist}
                </Typography>
              </Box>
            ))}
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowPlaylist(false)}>
            Cerrar
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
};

export default MusicPlayer;