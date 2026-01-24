# api2/utils/audio_processing.py
"""
Utilidades para procesamiento de archivos de audio
"""
import os
import numpy as np
import logging
from datetime import timedelta

try:
    import librosa
    LIBROSA_AVAILABLE = True
except ImportError:
    LIBROSA_AVAILABLE = False

try:
    import mutagen
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False

logger = logging.getLogger(__name__)


class AudioProcessor:
    """Procesador de archivos de audio"""
    
    def __init__(self, file_path):
        self.file_path = file_path
        self.analysis = {}
    
    def analyze(self):
        """Analiza el archivo de audio y extrae metadata"""
        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"Archivo no encontrado: {self.file_path}")
        
        try:
            # Análisis básico con mutagen
            self._analyze_with_mutagen()
            
            # Análisis avanzado con librosa (si está disponible)
            if LIBROSA_AVAILABLE:
                self._analyze_with_librosa()
            
            return self.analysis
            
        except Exception as e:
            logger.error(f"Error analizando audio {self.file_path}: {str(e)}")
            # Devolver análisis mínimo
            return {
                'is_valid': False,
                'error': str(e),
                'file_size': os.path.getsize(self.file_path)
            }
    
    def _analyze_with_mutagen(self):
        """Análisis básico con mutagen"""
        if not MUTAGEN_AVAILABLE:
            return
        
        try:
            audio = mutagen.File(self.file_path, easy=True)
            
            if audio is None:
                self.analysis['is_valid'] = False
                self.analysis['error'] = 'Formato de audio no reconocido'
                return
            
            # Información básica
            self.analysis['format'] = type(audio).__name__
            self.analysis['duration'] = audio.info.length
            self.analysis['bitrate'] = audio.info.bitrate // 1000 if audio.info.bitrate else 0
            
            # Información de canales y sample rate
            if hasattr(audio.info, 'channels'):
                self.analysis['channels'] = audio.info.channels
            
            if hasattr(audio.info, 'sample_rate'):
                self.analysis['sample_rate'] = audio.info.sample_rate
            
            self.analysis['is_valid'] = True
            
        except Exception as e:
            logger.warning(f"Error con mutagen: {str(e)}")
    
    def _analyze_with_librosa(self):
        """Análisis avanzado con librosa"""
        try:
            # Cargar audio (solo metadata, no los datos completos)
            y, sr = librosa.load(self.file_path, sr=None, mono=False, duration=30)
            
            self.analysis['librosa_sample_rate'] = sr
            
            # Calcular RMS (volumen promedio)
            if len(y.shape) > 1:  # Estéreo
                y_mono = librosa.to_mono(y)
            else:
                y_mono = y
            
            rms = librosa.feature.rms(y=y_mono)
            self.analysis['rms_mean'] = float(np.mean(rms))
            self.analysis['rms_std'] = float(np.std(rms))
            
            # Detectar silencios
            non_silent_intervals = librosa.effects.split(y_mono, top_db=30)
            self.analysis['non_silent_intervals'] = len(non_silent_intervals)
            
        except Exception as e:
            logger.debug(f"Librosa analysis failed: {str(e)}")
    
    @staticmethod
    def generate_waveform(file_path, num_points=800):
        """Genera datos de waveform para visualización"""
        if not LIBROSA_AVAILABLE:
            return None
        
        try:
            # Cargar audio
            y, sr = librosa.load(file_path, sr=None, mono=True)
            
            # Reducir muestras para waveform
            if len(y) > num_points:
                # Promediar bloques
                block_size = len(y) // num_points
                waveform = []
                
                for i in range(0, len(y) - block_size, block_size):
                    block = y[i:i + block_size]
                    waveform.append(float(np.max(np.abs(block))))
                
                # Asegurar longitud exacta
                waveform = waveform[:num_points]
            else:
                waveform = [float(abs(sample)) for sample in y[:num_points]]
            
            # Normalizar
            if waveform:
                max_val = max(waveform)
                if max_val > 0:
                    waveform = [val / max_val for val in waveform]
            
            return waveform
            
        except Exception as e:
            logger.warning(f"Error generando waveform: {str(e)}")
            return None
    
    @staticmethod
    def is_valid_audio(file_path):
        """Verifica rápidamente si es un archivo de audio válido"""
        try:
            if not os.path.exists(file_path):
                return False
            
            # Verificar tamaño mínimo (1KB)
            if os.path.getsize(file_path) < 1024:
                return False
            
            # Intentar analizar con mutagen
            if MUTAGEN_AVAILABLE:
                audio = mutagen.File(file_path)
                return audio is not None and hasattr(audio, 'info')
            
            # Fallback: verificar extensión
            audio_extensions = {'.mp3', '.wav', '.ogg', '.flac', '.m4a', '.aac'}
            _, ext = os.path.splitext(file_path)
            return ext.lower() in audio_extensions
            
        except Exception:
            return False