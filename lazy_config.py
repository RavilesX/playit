import os
import psutil
from dataclasses import dataclass
from typing import Dict, Any
from pathlib import Path
import time


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

    # Configuración de debugging
    enable_debug_logging: bool = False
    stats_update_interval: int = 5  # segundos

    @classmethod
    def create_adaptive_config(cls) -> 'LazyLoadingConfig':
        """Crea configuración adaptada a los recursos del sistema"""
        try:
            # Obtener información del sistema
            memory_gb = psutil.virtual_memory().total / (1024 ** 3)
            cpu_count = psutil.cpu_count()

            config = cls()

            # Ajustar según memoria disponible
            if memory_gb < 4:
                # Sistema con poca memoria
                config.audio_cache_size = 8
                config.image_cache_size = 30
                config.lyrics_cache_size = 15
                config.max_memory_usage_mb = 256
                config.preload_next_songs = 1
                config.preload_covers = False
                config.max_concurrent_loads = 1

            elif memory_gb < 8:
                # Sistema con memoria media
                config.audio_cache_size = 15
                config.image_cache_size = 75
                config.lyrics_cache_size = 35
                config.max_memory_usage_mb = 384
                config.preload_next_songs = 2
                config.preload_covers = True
                config.max_concurrent_loads = 2

            else:
                # Sistema con mucha memoria
                config.audio_cache_size = 25
                config.image_cache_size = 150
                config.lyrics_cache_size = 75
                config.max_memory_usage_mb = 768
                config.preload_next_songs = 3
                config.preload_covers = True
                config.max_concurrent_loads = 3

            # Ajustar según CPU
            if cpu_count < 4:
                config.max_concurrent_loads = max(1, config.max_concurrent_loads - 1)
                config.enable_threading = True
            else:
                config.max_concurrent_loads = min(cpu_count, 5)
                config.enable_threading = True

            # Habilitar debug en desarrollo
            if os.getenv('PLAYIT_DEBUG', '').lower() in ['1', 'true', 'yes']:
                config.enable_debug_logging = True
                #print("🐛 Debug logging habilitado")

            return config

        except Exception as e:
            # Configuración conservadora por defecto
            config = cls()
            config.audio_cache_size = 10
            config.image_cache_size = 50
            config.lyrics_cache_size = 25
            config.max_memory_usage_mb = 256
            config.preload_next_songs = 1
            config.max_concurrent_loads = 1
            return config

    def save_to_file(self, filepath: Path):
        """Guarda la configuración en un archivo con manejo de errores"""
        try:
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
                'load_timeout_seconds': self.load_timeout_seconds,
                'enable_debug_logging': self.enable_debug_logging,
                'stats_update_interval': self.stats_update_interval,
                'created_at': time.strftime('%Y-%m-%d %H:%M:%S')
            }

            # Crear directorio si no existe
            filepath.parent.mkdir(parents=True, exist_ok=True)

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(config_dict, f, indent=4, ensure_ascii=False)


        except Exception as e:
            print(f"❌ Error guardando configuración: {e}")

    @classmethod
    def load_from_file(cls, filepath: Path) -> 'LazyLoadingConfig':
        """Carga configuración desde archivo con validación"""
        try:
            import json

            if not filepath.exists():
                return cls.create_adaptive_config()

            with open(filepath, 'r', encoding='utf-8') as f:
                config_dict = json.load(f)

            config = cls()

            # Validar y aplicar cada configuración
            for key, value in config_dict.items():
                if hasattr(config, key) and key != 'created_at':
                    # Validación básica de tipos
                    expected_type = type(getattr(config, key))
                    if isinstance(value, expected_type):
                        setattr(config, key, value)

            return config

        except Exception as e:
            return cls.create_adaptive_config()


class MemoryMonitor:
    """Monitor de memoria para lazy loading"""

    def __init__(self, config: LazyLoadingConfig):
        self.config = config
        self.process = psutil.Process()
        self.last_check = 0
        self._memory_history = []
        self._max_history = 10

    def get_memory_usage_mb(self) -> float:
        """Obtiene el uso actual de memoria en MB"""
        try:
            memory_info = self.process.memory_info()
            usage_mb = memory_info.rss / (1024 * 1024)

            # Mantener historial para tendencias
            self._memory_history.append(usage_mb)
            if len(self._memory_history) > self._max_history:
                self._memory_history.pop(0)

            return usage_mb
        except Exception as e:
            return 0.0

    def get_memory_trend(self) -> str:
        """Determina la tendencia de uso de memoria"""
        if len(self._memory_history) < 3:
            return "stable"

        recent_avg = sum(self._memory_history[-3:]) / 3
        older_avg = sum(self._memory_history[:-3]) / max(1, len(self._memory_history) - 3)

        if recent_avg > older_avg * 1.1:
            return "increasing"
        elif recent_avg < older_avg * 0.9:
            return "decreasing"
        else:
            return "stable"

    def should_cleanup(self) -> bool:
        """Determina si se debe hacer limpieza de memoria"""
        current_usage = self.get_memory_usage_mb()
        threshold = self.config.max_memory_usage_mb

        # Limpieza preventiva si la tendencia es creciente
        trend = self.get_memory_trend()
        if trend == "increasing" and current_usage > threshold * 0.8:
            return True

        return current_usage > threshold

    def get_cleanup_priority(self) -> Dict[str, int]:
        """Retorna prioridades de limpieza mejoradas (1=alta, 3=baja)"""
        current_usage = self.get_memory_usage_mb()
        percentage = current_usage / self.config.max_memory_usage_mb
        trend = self.get_memory_trend()

        if percentage > 0.9 or trend == "increasing":
            # Limpieza agresiva - priorizar audio que consume más memoria
            return {"audio": 1, "images": 2, "lyrics": 3}
        elif percentage > 0.75:
            # Limpieza moderada - balancear imágenes y audio
            return {"images": 1, "audio": 2, "lyrics": 3}
        else:
            # Limpieza suave - solo letras (menos impacto)
            return {"lyrics": 1, "images": 2, "audio": 3}

    def get_system_memory_info(self) -> Dict[str, Any]:
        """Obtiene información completa del sistema"""
        try:
            virtual = psutil.virtual_memory()
            return {
                'total_gb': virtual.total / (1024 ** 3),
                'available_gb': virtual.available / (1024 ** 3),
                'percent_used': virtual.percent,
                'process_usage_mb': self.get_memory_usage_mb(),
                'memory_trend': self.get_memory_trend()
            }
        except Exception as e:
            return {}


class LazyLoadingOptimizer:
    """Optimizador de rendimiento para lazy loading"""
    def __init__(self, config: LazyLoadingConfig):
        self.config = config
        self.load_times: Dict[str, list] = {}
        self.hit_rates: Dict[str, float] = {}
        self.memory_monitor = MemoryMonitor(config)
        self._optimization_history = []

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

        times = self.load_times[resource_type]
        return sum(times) / len(times)

    def get_performance_metrics(self) -> Dict[str, Any]:
        """Obtiene métricas completas de rendimiento"""
        metrics = {}

        for resource_type in ['audio', 'images', 'lyrics']:
            avg_time = self.get_average_load_time(resource_type)
            times = self.load_times.get(resource_type, [])

            metrics[resource_type] = {
                'avg_load_time': avg_time,
                'total_loads': len(times),
                'min_time': min(times) if times else 0,
                'max_time': max(times) if times else 0,
                'performance_rating': self._calculate_performance_rating(avg_time)
            }

        return metrics

    def _calculate_performance_rating(self, avg_time: float) -> str:
        """Califica el rendimiento basado en tiempo promedio"""
        if avg_time < 0.1:
            return "excellent"
        elif avg_time < 0.5:
            return "good"
        elif avg_time < 1.0:
            return "fair"
        else:
            return "poor"

    def suggest_cache_adjustments(self) -> Dict[str, Any]:
        """Sugiere ajustes de tamaño de cache basado en rendimiento"""
        suggestions = {}
        memory_info = self.memory_monitor.get_system_memory_info()

        for resource_type in ['audio', 'image', 'lyrics']:
            avg_time = self.get_average_load_time(resource_type)
            current_size = getattr(self.config, f"{resource_type}_cache_size")

            if avg_time > 2.0:  # Si tarda más de 2 segundos
                # Sugerir aumentar cache si hay memoria disponible
                if memory_info.get('percent_used', 100) < 80:
                    new_size = min(current_size + 10, int(current_size * 1.5))
                    suggestions[f"{resource_type}_cache_size"] = new_size
                    suggestions[f"{resource_type}_reason"] = "Slow loading detected"

            elif avg_time < 0.1 and memory_info.get('percent_used', 0) > 85:
                # Puede reducir cache si hay presión de memoria
                new_size = max(5, int(current_size * 0.8))
                suggestions[f"{resource_type}_cache_size"] = new_size
                suggestions[f"{resource_type}_reason"] = "Fast loading + high memory usage"

        return suggestions

    def optimize_preloading(self, playlist_size: int, current_index: int) -> Dict[str, Any]:
        """Optimiza estrategia de preloading basado en condiciones actuales"""
        memory_usage = self.memory_monitor.get_memory_usage_mb()
        memory_percentage = memory_usage / self.config.max_memory_usage_mb
        memory_trend = self.memory_monitor.get_memory_trend()

        optimization = {
            'preload_audio': True,
            'preload_lyrics': True,
            'preload_covers': True,
            'preload_count': self.config.preload_next_songs
        }

        # Ajustar según uso de memoria y tendencia
        if memory_percentage > 0.9 or memory_trend == "increasing":
            optimization['preload_count'] = 1
            optimization['preload_covers'] = False
            optimization['preload_audio'] = current_index % 2 == 0  # Solo cada 2 canciones

        elif memory_percentage > 0.7:
            optimization['preload_count'] = 2
            optimization['preload_covers'] = current_index % 2 == 0

        # Ajustar según posición en playlist
        remaining_songs = playlist_size - current_index - 1
        if remaining_songs < optimization['preload_count']:
            optimization['preload_count'] = max(0, remaining_songs)

        # Registrar optimización para análisis
        self._optimization_history.append({
            'timestamp': time.time(),
            'memory_percentage': memory_percentage,
            'memory_trend': memory_trend,
            'optimization': optimization.copy()
        })

        # Mantener solo los últimos 20 registros
        if len(self._optimization_history) > 20:
            self._optimization_history = self._optimization_history[-20:]

        return optimization

    def get_optimization_report(self) -> str:
        """Genera reporte detallado de optimizaciones"""
        if not self._optimization_history:
            return "No hay datos de optimización disponibles"

        recent = self._optimization_history[-5:]  # Últimas 5 optimizaciones

        report_lines = ["📊 REPORTE DE OPTIMIZACIÓN LAZY LOADING", "=" * 50]

        # Métricas de rendimiento
        metrics = self.get_performance_metrics()
        for resource_type, data in metrics.items():
            report_lines.extend([
                f"\n🔹 {resource_type.upper()}:",
                f"  ├─ Tiempo promedio: {data['avg_load_time']:.3f}s",
                f"  ├─ Total cargas: {data['total_loads']}",
                f"  ├─ Rango: {data['min_time']:.3f}s - {data['max_time']:.3f}s",
                f"  └─ Rating: {data['performance_rating']}"
            ])

        # Información de memoria
        memory_info = self.memory_monitor.get_system_memory_info()
        report_lines.extend([
            f"\n💾 MEMORIA:",
            f"  ├─ Sistema: {memory_info.get('total_gb', 0):.1f}GB total",
            f"  ├─ Disponible: {memory_info.get('available_gb', 0):.1f}GB",
            f"  ├─ Uso del sistema: {memory_info.get('percent_used', 0):.1f}%",
            f"  ├─ Proceso actual: {memory_info.get('process_usage_mb', 0):.1f}MB",
            f"  └─ Tendencia: {memory_info.get('memory_trend', 'unknown')}"
        ])

        # Sugerencias de optimización
        suggestions = self.suggest_cache_adjustments()
        if suggestions:
            report_lines.extend(["\n⚙️ SUGERENCIAS DE OPTIMIZACIÓN:"])
            for key, value in suggestions.items():
                if not key.endswith('_reason'):
                    reason = suggestions.get(f"{key}_reason", "")
                    report_lines.append(f"  ├─ {key}: {value} ({reason})")

        # Historial reciente de optimizaciones
        if recent:
            report_lines.extend(["\n🕐 OPTIMIZACIONES RECIENTES:"])
            for i, opt in enumerate(recent[-3:], 1):  # Solo las últimas 3
                timestamp = time.strftime('%H:%M:%S', time.localtime(opt['timestamp']))
                report_lines.extend([
                    f"  {i}. {timestamp} - Memoria: {opt['memory_percentage']:.1f}%",
                    f"     └─ Preload: {opt['optimization']['preload_count']} canciones"
                ])

        return "\n".join(report_lines)


class LazyLoadingBestPractices:
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
    try:
        # Crear configuración adaptativa
        config = LazyLoadingConfig.create_adaptive_config()

        # Guardar configuración para referencia
        config_path = Path("config") / "lazy_loading_config.json"
        config.save_to_file(config_path)

        # Aplicar configuración a los gestores
        if hasattr(audioplayer_instance, 'lazy_audio'):
            audioplayer_instance.lazy_audio.cache.max_size = config.audio_cache_size
        if hasattr(audioplayer_instance, 'lazy_images'):
            audioplayer_instance.lazy_images.cache.max_size = config.image_cache_size
        if hasattr(audioplayer_instance, 'lazy_lyrics'):
            audioplayer_instance.lazy_lyrics.cache.max_size = config.lyrics_cache_size

        # Configurar monitoring y optimización
        optimizer = LazyLoadingOptimizer(config)
        audioplayer_instance.lazy_optimizer = optimizer
        audioplayer_instance.lazy_config = config

        # Timer para optimización automática
        from PyQt6.QtCore import QTimer
        optimization_timer = QTimer()
        optimization_timer.timeout.connect(
            lambda: apply_auto_optimizations(audioplayer_instance, optimizer)
        )
        optimization_timer.start(config.memory_check_interval_ms)

        # Timer para estadísticas de debug (solo si está habilitado)
        if config.enable_debug_logging:
            debug_timer = QTimer()
            debug_timer.timeout.connect(
                lambda: print(f"\n{optimizer.get_optimization_report()}\n")
            )
            debug_timer.start(30000)  # Cada 30 segundos
            #print("🐛 Timer de debug habilitado")

        # Asignar timers para limpieza posterior
        audioplayer_instance.optimization_timer = optimization_timer
        if config.enable_debug_logging:
            audioplayer_instance.debug_timer = debug_timer

        return True

    except Exception as e:
        return False


def apply_auto_optimizations(player, optimizer):
    """Aplica optimizaciones automáticas basadas en métricas"""
    # Verificar si necesita limpieza de memoria
    if optimizer.memory_monitor.should_cleanup():
        priorities = optimizer.memory_monitor.get_cleanup_priority()

        # Aplicar limpieza según prioridades
        cleaned_items = 0

        if priorities.get("audio", 3) == 1 and hasattr(player, 'lazy_audio'):
            before_size = len(player.lazy_audio.cache._cache)
            if hasattr(player, 'current_index') and player.current_index >= 0:
                current_path = player.playlist[player.current_index]["path"]
                player.lazy_audio.cleanup_old_audio(Path(current_path))
            after_size = len(player.lazy_audio.cache._cache)
            cleaned_items += before_size - after_size

        if priorities.get("images", 3) == 1 and hasattr(player, 'lazy_images'):
            before_size = len(player.lazy_images.cache._cache)
            player.lazy_images.cache._cleanup_if_needed()
            after_size = len(player.lazy_images.cache._cache)
            cleaned_items += before_size - after_size

        if priorities.get("lyrics", 3) == 1 and hasattr(player, 'lazy_lyrics'):
            before_size = len(player.lazy_lyrics.cache._cache)
            player.lazy_lyrics.cache._cleanup_if_needed()
            after_size = len(player.lazy_lyrics.cache._cache)
            cleaned_items += before_size - after_size

    # Aplicar sugerencias de optimización periódicamente
    suggestions = optimizer.suggest_cache_adjustments()
    if suggestions and hasattr(player, 'lazy_config'):
        applied_changes = []

        for key, value in suggestions.items():
            if not key.endswith('_reason') and hasattr(player.lazy_config, key):
                old_value = getattr(player.lazy_config, key)
                if abs(old_value - value) > 2:  # Solo cambios significativos
                    setattr(player.lazy_config, key, value)
                    applied_changes.append(f"{key}: {old_value} → {value}")


# TESTING Y DEBUG

# def benchmark_lazy_loading():
#     """Benchmark de rendimiento del lazy loading"""
#     try:
#         from lazy_resources import ResourceCache
#         import time
#         import threading
#
#         # Test de cache básico
#         cache = ResourceCache(max_size=10)
#
#         def dummy_loader():
#             time.sleep(0.1)  # Simular carga
#             return f"resource_{time.time()}"
#
#         # Test secuencial
#         start_time = time.time()
#         for i in range(20):
#             cache.get(f"key_{i}", dummy_loader)
#         sequential_time = time.time() - start_time
#
#         # Test concurrente
#         cache.clear()
#         start_time = time.time()
#
#         def load_worker(start_idx):
#             for i in range(start_idx, start_idx + 5):
#                 cache.get(f"key_{i}", dummy_loader)
#
#         threads = []
#         for i in range(0, 20, 5):
#             t = threading.Thread(target=load_worker, args=(i,))
#             threads.append(t)
#             t.start()
#
#         for t in threads:
#             t.join()
#
#         concurrent_time = time.time() - start_time
#
#     except Exception as e:
#         print(f"❌ Error en benchmark: {e}")
#
#
# if __name__ == "__main__":
#     # Ejecutar benchmark si se llama directamente
#     benchmark_lazy_loading()