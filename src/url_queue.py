import threading
import time
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime


@dataclass
class UrlTask:
    """Задача обработки URL"""
    url: str
    source: str = "unknown"
    added_at: datetime = None
    task_id: str = None
    
    def __post_init__(self):
        if self.added_at is None:
            self.added_at = datetime.now()
        if self.task_id is None:
            self.task_id = f"{self.source}_{int(time.time())}"


class UrlQueue:
    """
    Универсальная thread-safe очередь URL для обработки
    Не зависит от источника ввода (Telegram, Web, Console, etc.)
    """
    
    def __init__(self, max_size: int = 5):
        """
        Args:
            max_size: максимальный размер очереди
        """
        self.max_size = max_size
        self._queue: List[UrlTask] = []
        self._lock = threading.Lock()
        self._processing_task: Optional[UrlTask] = None
    
    def add_url(self, url: str, source: str = "unknown") -> Dict[str, Any]:
        """
        Добавляет URL в очередь
        
        Args:
            url: URL для обработки
            source: источник URL (telegram, web, console, etc.)
            
        Returns:
            Dict с результатом:
            {
                'success': bool,
                'message': str,
                'task_id': str,
                'position': int,  # позиция в очереди
                'queue_size': int
            }
        """
        with self._lock:
            if len(self._queue) >= self.max_size:
                return {
                    'success': False,
                    'message': f'Очередь переполнена (максимум {self.max_size} ссылок)',
                    'task_id': None,
                    'position': -1,
                    'queue_size': len(self._queue)
                }
            
            task = UrlTask(url=url, source=source)
            self._queue.append(task)
            
            return {
                'success': True,
                'message': f'URL добавлен в очередь',
                'task_id': task.task_id,
                'position': len(self._queue),
                'queue_size': len(self._queue)
            }
    
    def get_next_url(self) -> Optional[UrlTask]:
        """
        Извлекает следующий URL для обработки
        
        Returns:
            UrlTask или None если очередь пуста
        """
        with self._lock:
            if not self._queue:
                return None
                
            task = self._queue.pop(0)
            self._processing_task = task
            return task
    
    def mark_completed(self, task_id: str) -> bool:
        """
        Отмечает задачу как завершенную
        
        Args:
            task_id: ID завершенной задачи
            
        Returns:
            True если задача была в обработке
        """
        with self._lock:
            if (self._processing_task and 
                self._processing_task.task_id == task_id):
                self._processing_task = None
                return True
            return False
    
    def get_queue_status(self) -> Dict[str, Any]:
        """
        Возвращает текущий статус очереди
        
        Returns:
            Dict со статусом очереди
        """
        with self._lock:
            return {
                'queue_size': len(self._queue),
                'max_size': self.max_size,
                'is_full': len(self._queue) >= self.max_size,
                'is_empty': len(self._queue) == 0,
                'processing_task': (
                    self._processing_task.task_id if self._processing_task else None
                ),
                'waiting_tasks': [
                    {
                        'task_id': task.task_id,
                        'url': task.url,
                        'source': task.source,
                        'added_at': task.added_at.strftime('%H:%M:%S')
                    }
                    for task in self._queue
                ]
            }
    
    def clear_queue(self) -> Dict[str, Any]:
        """
        Очищает очередь (не влияет на текущую обработку)
        
        Returns:
            Dict с результатом очистки
        """
        with self._lock:
            cleared_count = len(self._queue)
            self._queue.clear()
            
            return {
                'success': True,
                'message': f'Очередь очищена ({cleared_count} задач удалено)',
                'cleared_count': cleared_count
            }
    
    def get_position(self, task_id: str) -> Optional[int]:
        """
        Возвращает позицию задачи в очереди
        
        Args:
            task_id: ID задачи
            
        Returns:
            Позиция в очереди (1-based) или None если не найдена
        """
        with self._lock:
            for i, task in enumerate(self._queue):
                if task.task_id == task_id:
                    return i + 1
            return None
    
    def remove_task(self, task_id: str) -> Dict[str, Any]:
        """
        Удаляет задачу из очереди
        
        Args:
            task_id: ID задачи для удаления
            
        Returns:
            Dict с результатом удаления
        """
        with self._lock:
            for i, task in enumerate(self._queue):
                if task.task_id == task_id:
                    removed_task = self._queue.pop(i)
                    return {
                        'success': True,
                        'message': f'Задача {task_id} удалена из очереди',
                        'removed_task': {
                            'url': removed_task.url,
                            'source': removed_task.source
                        }
                    }
            
            return {
                'success': False,
                'message': f'Задача {task_id} не найдена в очереди',
                'removed_task': None
            }


# Глобальный экземпляр очереди для использования во всем приложении
url_queue = UrlQueue(max_size=5)