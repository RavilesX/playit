import os
import psutil
from dataclasses import dataclass
from typing import Dict, Any
from pathlib import Path


@dataclass
class LazyLoadingConfig:
    """Configuración adaptable para lazy loading basada en recursos del sistema"""

    # Tamaños de cache por defecto
    audio_cache_size: int = 20
    image_cache_size: int = 100
    lyrics_cache_size: int = 50

    # Configuración de preloading
    preload_next_songs: int = 2
    preload_adjacent_lyrics: bool = True
    preload_covers: bool = True

    # Configuración de limpieza
    cleanup_interval_ms: int = 300000  # 5 minutos
    aggressive_cleanup_threshold: int = 150

    # Configuración de memoria
    max_memory_usage_mb: int = 512
    memory_check_interval_ms: int = 60000  # 1 minuto

    # Configuración de rendimiento
    enable_threading: bool = True
    max_concurrent_loads: int = 3
    load_timeout_seconds: int = 30

    @classmethod
    def create_adaptive_config(cls) -> 'LazyLoadingConfig':
        """Crea configuración adaptada a los recursos del sistema"""

        # Obtener información del sistema
        memory_gb = psutil.virtual_memory().total / (1024 ** 3)
        cpu_count = psutil.cpu_count()

        config = cls()

        # Ajustar según memoria disponible
        if memory_gb < 4:
            # Sistema con poca memoria
            config.audio_cache_size = 10
            config.image_cache_size = 50
            config.lyrics_cache_size = 25
            config.max_memory_usage_mb = 256
            config.preload_next_songs = 1

        elif memory_gb < 8:
            # Sistema con memoria media
            config.audio_cache_size = 15
            config.image_cache_size = 75
            config.lyrics_cache_size = 35
            config.max_memory_usage_mb = 384
            config.preload_next_songs = 2

        else:
            # Sistema con mucha memoria
            config.audio_cache_size = 25
            config.image_cache_size = 150
            config.lyrics_cache_size = 75
            config.max_memory_usage_mb = 768
            config.preload_next_songs = 3

        # Ajustar según CPU
        if cpu_count < 4:
            config.max_concurrent_loads = 2
            config.enable_threading = True
        else:
            config.max_concurrent_loads = min(cpu_count, 5)
            config.enable_threading = True

        return config

    def save_to_file(self, filepath: Path):
        """Guarda la configuración en un archivo"""
        import json
        config_dict = {
            'audio_cache_size': self.audio_cache_size,
            'image_cache_size': self.image_cache_size,
            'lyrics_cache_size': self.lyrics_cache_size,
            'preload_next_songs': self.preload_next_songs,
            'preload_adjacent_lyrics': self.preload_adjacent_lyrics,
            'preload_covers': self.preload_covers,
            'cleanup_interval_ms': self.cleanup_interval_ms,
            'aggressive_cleanup_threshold': self.aggressive_cleanup_threshold,
            'max_memory_usage_mb': self.max_memory_usage_mb,
            'memory_check_interval_ms': self.memory_check_interval_ms,
            'enable_threading': self.enable_threading,
            'max_concurrent_loads': self.max_concurrent_loads,
            'load_timeout_seconds': self.load_timeout_seconds
        }

        with open(filepath, 'w') as f:
            json.dump(config_dict, f, indent=4)

    @classmethod
    def load_from_file(cls, filepath: Path) -> 'LazyLoadingConfig':
        """Carga configuración desde archivo"""
        import json
        try:
            with open(filepath, 'r') as f:
                config_dict = json.load(f)

            config = cls()
            for key, value in config_dict.items():
                if hasattr(config, key):
                    setattr(config, key, value)

            return config
        except Exception as e:
            print(f"Error cargando configuración: {e}, usando valores por defecto")
            return cls.create_adaptive_config()


class MemoryMonitor:
    """Monitor de memoria para lazy loading"""

    def __init__(self, config: LazyLoadingConfig):
        self.config = config
        self.process = psutil.Process()
        self.last_check = 0

    def get_memory_usage_mb(self) -> float:
        """Obtiene el uso actual de memoria en MB"""
        return self.process.memory_info().rss / (1024 * 1024)

    def should_cleanup(self) -> bool:
        """Determina si se debe hacer limpieza de memoria"""
        current_usage = self.get_memory_usage_mb()
        return current_usage > self.config.max_memory_usage_mb

    def get_cleanup_priority(self) -> Dict[str, int]:
        """Retorna prioridades de limpieza (1=alta, 3=baja)"""
        current_usage = self.get_memory_usage_mb()
        percentage = current_usage / self.config.max_memory_usage_mb

        if percentage > 0.9:
            # Limpieza agresiva
            return {"audio": 1, "images": 2, "lyrics": 3}
        elif percentage > 0.75:
            # Limpieza moderada
            return {"audio": 2, "images": 1, "lyrics": 3}
        else:
            # Limpieza suave
            return {"audio": 3, "images": 2, "lyrics": 1}


class LazyLoadingOptimizer:
    """Optimizador de rendimiento para lazy loading"""

    def __init__(self, config: LazyLoadingConfig):
        self.config = config
        self.load_times: Dict[str, float] = {}
        self.hit_rates: Dict[str, float] = {}
        self.memory_monitor = MemoryMonitor(config)

    def record_load_time(self, resource_type: str, load_time: float):
        """Registra tiempo de carga para análisis"""
        if resource_type not in self.load_times:
            self.load_times[resource_type] = []

        self.load_times[resource_type].append(load_time)

        # Mantener solo los últimos 50 registros
        if len(self.load_times[resource_type]) > 50:
            self.load_times[resource_type] = self.load_times[resource_type][-50:]

    def get_average_load_time(self, resource_type: str) -> float:
        """Obtiene el tiempo promedio de carga"""
        if resource_type not in self.load_times or not self.load_times[resource_type]:
            return 0.0

        return sum(self.load_times[resource_type]) / len(self.load_times[resource_type])

    def suggest_cache_adjustments(self) -> Dict[str, int]:
        """Sugiere ajustes de tamaño de cache basado en rendimiento"""
        suggestions = {}

        # Analizar tiempos de carga
        for resource_type in ['audio', 'images', 'lyrics']:
            avg_time = self.get_average_load_time(resource_type)

            if avg_time > 2.0:  # Si tarda más de 2 segundos
                # Sugerir aumentar cache
                current_size = getattr(self.config, f"{resource_type}_cache_size")
                suggestions[f"{resource_type}_cache_size"] = min(current_size + 10, current_size * 1.5)
            elif avg_time < 0.1:  # Si es muy rápido
                # Puede reducir cache
                current_size = getattr(self.config, f"{resource_type}_cache_size")
                suggestions[f"{resource_type}_cache_size"] = max(current_size - 5, current_size * 0.8)

        return suggestions

    def optimize_preloading(self, playlist_size: int, current_index: int) -> Dict[str, Any]:
        """Optimiza estrategia de preloading"""
        memory_usage = self.memory_monitor.get_memory_usage_mb()
        memory_percentage = memory_usage / self.config.max_memory_usage_mb

        optimization = {
            'preload_audio': True,
            'preload_lyrics': True,
            'preload_covers': True,
            'preload_count': self.config.preload_next_songs
        }

        # Ajustar según uso de memoria
        if memory_percentage > 0.8:
            optimization['preload_count'] = 1
            optimization['preload_covers'] = False
        elif memory_percentage > 0.6:
            optimization['preload_count'] = 2
            optimization['preload_covers'] = current_index % 2 == 0  # Solo cada 2 canciones

        # Ajustar según posición en playlist
        remaining_songs = playlist_size - current_index
        if remaining_songs < optimization['preload_count']:
            optimization['preload_count'] = remaining_songs

        return optimization


# MEJORES PRÁCTICAS DE IMPLEMENTACIÓN

class LazyLoadingBestPractices:
    """
    Mejores prácticas para implementar lazy loading en AudioPlayer
    """

    @staticmethod
    def get_implementation_tips() -> Dict[str, str]:
        return {
            "1_Inicialización": """
            - Inicializar gestores de lazy loading ANTES que la UI
            - Usar configuración adaptativa basada en recursos del sistema
            - Establecer límites de memoria apropiados desde el inicio
            """,

            "2_Carga_Prioritaria": """
            - Cargar primero los recursos críticos (UI, iconos básicos)
            - Usar preloading inteligente para recursos probables
            - Implementar timeouts para evitar bloqueos
            """,

            "3_Gestión_Memoria": """
            - Monitorear uso de memoria constantemente
            - Implementar limpieza automática basada en LRU
            - Usar WeakReferences donde sea apropiado
            """,

            "4_Threading": """
            - Nunca bloquear el hilo principal con carga de recursos
            - Usar hilos daemon para preloading
            - Implementar locks apropiados para thread safety
            """,

            "5_Cache_Strategy": """
            - Implementar cache híbrido (memoria + disco para recursos grandes)
            - Usar diferentes estrategias por tipo de recurso
            - Implementar versionado de cache para actualizaciones
            """,

            "6_Error_Handling": """
            - Siempre tener fallbacks para recursos faltantes
            - Implementar retry con backoff exponencial
            - Registrar errores para debugging sin bloquear la app
            """,

            "7_Performance_Monitoring": """
            - Registrar métricas de rendimiento
            - Implementar profiling opcional para desarrollo
            - Usar métricas para ajuste automático de parámetros
            """,

            "8_User_Experience": """
            - Mostrar indicadores de carga apropiados
            - Implementar carga progresiva (placeholder → baja calidad → alta calidad)
            - Priorizar recursos visibles sobre los no visibles
            """
        }

    @staticmethod
    def get_common_pitfalls() -> Dict[str, str]:
        return {
            "Memory_Leaks": """
            - No limpiar referencias circulares
            - No remover listeners de eventos
            - Mantener referencias a objetos grandes innecesariamente
            """,

            "Thread_Issues": """
            - Acceder a UI desde hilos secundarios
            - No sincronizar acceso a recursos compartidos
            - Crear demasiados hilos concurrentes
            """,

            "Cache_Problems": """
            - No implementar límites de tamaño
            - No considerar invalidación de cache
            - Cache demasiado agresivo causando uso excesivo de memoria
            """,

            "Performance_Issues": """
            - Cargar recursos síncronamente en el hilo principal
            - No implementar debouncing para operaciones frecuentes
            - Cache ineficiente con claves mal diseñadas
            """
        }


# EJEMPLO DE CONFIGURACIÓN COMPLETA

def setup_production_lazy_loading(audioplayer_instance):
    """
    Configuración optimizada para producción
    """
    # Crear configuración adaptativa
    config = LazyLoadingConfig.create_adaptive_config()

    # Guardar configuración para referencia
    config_path = Path("lazy_loading_config.json")
    config.save_to_file(config_path)

    # Aplicar configuración a los gestores
    audioplayer_instance.lazy_audio.cache.max_size = config.audio_cache_size
    audioplayer_instance.lazy_images.cache.max_size = config.image_cache_size
    audioplayer_instance.lazy_lyrics.cache.max_size = config.lyrics_cache_size

    # Configurar monitoring
    optimizer = LazyLoadingOptimizer(config)
    audioplayer_instance.lazy_optimizer = optimizer

    # Timer para optimización automática
    from PyQt6.QtCore import QTimer
    optimization_timer = QTimer()
    optimization_timer.timeout.connect(
        lambda: apply_auto_optimizations(audioplayer_instance, optimizer)
    )
    optimization_timer.start(config.memory_check_interval_ms)

    print(f"Lazy loading configurado: Audio={config.audio_cache_size}, "
          f"Images={config.image_cache_size}, Lyrics={config.lyrics_cache_size}")


def apply_auto_optimizations(player, optimizer):
    """Aplica optimizaciones automáticas basadas en métricas"""
    try:
        if optimizer.memory_monitor.should_cleanup():
            priorities = optimizer.memory_monitor.get_cleanup_priority()

            # Aplicar limpieza según prioridades
            if priorities["audio"] == 1:
                player.lazy_audio.cache._cleanup_if_needed()

            if priorities["images"] == 1:
                player.lazy_images.cache._cleanup_if_needed()

            if priorities["lyrics"] == 1:
                player.lazy_lyrics.cache._cleanup_if_needed()

    except Exception as e:
        print(f"Error en optimización automática: {e}")


# TESTING Y DEBUG

def create_debug_audioplayer():
    """Crea AudioPlayer con debugging habilitado"""
    from main import AudioPlayer

    player = AudioPlayer()

    # Habilitar logging detallado
    import logging
    logging.basicConfig(level=logging.DEBUG)

    # Timer para mostrar estadísticas
    from PyQt6.QtCore import QTimer
    debug_timer = QTimer()
    debug_timer.timeout.connect(lambda: print(player.show_cache_debug_info()))
    debug_timer.start(10000)  # Cada 10 segundos

    return player