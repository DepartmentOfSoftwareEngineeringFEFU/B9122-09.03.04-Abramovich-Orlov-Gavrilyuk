"""
Сервис построения навигационного графа
Использует алгоритм A* для поиска маршрутов
"""

from typing import List, Tuple, Dict, Optional, Set
from dataclasses import dataclass
import heapq
import math

try:
    import networkx as nx
except ImportError:
    nx = None


@dataclass
class GraphNode:
    """Вершина навигационного графа"""
    id: int
    x: float
    y: float
    z: int  # Номер этажа
    node_type: str  # room, corridor, door, stairs, elevator
    room_number: Optional[str] = None


@dataclass
class GraphEdge:
    """Ребро навигационного графа"""
    id: int
    source_id: int
    target_id: int
    weight: float  # Расстояние в метрах


class NavigationGraphService:
    """
    Сервис построения и работы с навигационным графом
    
    Создаёт граф из векторной модели и ищет маршруты
    """
    
    def __init__(self):
        self.nodes: Dict[int, GraphNode] = {}
        self.edges: List[GraphEdge] = {}
        self.adjacency: Dict[int, List[Tuple[int, float]]] = {}
    
    def add_node(self, node: GraphNode) -> None:
        """Добавление вершины"""
        self.nodes[node.id] = node
        if node.id not in self.adjacency:
            self.adjacency[node.id] = []
    
    def add_edge(self, edge: GraphEdge) -> None:
        """Добавление ребра (двунаправленное)"""
        self.edges[edge.id] = edge
        self.adjacency[edge.source_id].append((edge.target_id, edge.weight))
        self.adjacency[edge.target_id].append((edge.source_id, edge.weight))
    
    @staticmethod
    def euclidean_distance(
        node1: GraphNode, 
        node2: GraphNode
    ) -> float:
        """Евклидово расстояние между вершинами"""
        return math.sqrt(
            (node1.x - node2.x) ** 2 + 
            (node1.y - node2.y) ** 2
        )
    
    @staticmethod
    def manhattan_distance(
        node1: GraphNode, 
        node2: GraphNode
    ) -> float:
        """Манхэттенское расстояние (для коридоров)"""
        return abs(node1.x - node2.x) + abs(node1.y - node2.y)
    
    def find_node_by_room(self, room_number: str) -> Optional[GraphNode]:
        """Поиск вершины по номеру комнаты"""
        for node in self.nodes.values():
            if node.room_number == room_number.upper():
                return node
        return None
    
    def a_star(
        self, 
        start_id: int, 
        goal_id: int,
        heuristic: str = "manhattan"
    ) -> Optional[List[int]]:
        """
        Алгоритм A* для поиска кратчайшего пути
        
        Args:
            start_id: ID начальной вершины
            goal_id: ID конечной вершины
            heuristic: "manhattan" или "euclidean"
            
        Returns:
            Список ID вершин маршрута или None
        """
        if start_id not in self.nodes or goal_id not in self.nodes:
            return None
        
        goal = self.nodes[goal_id]
        
        # Выбор эвристики
        if heuristic == "manhattan":
            h = lambda n: self.manhattan_distance(self.nodes[n], goal)
        else:
            h = lambda n: self.euclidean_distance(self.nodes[n], goal)
        
        # Инициализация
        open_set: List[Tuple[float, int]] = [(0, start_id)]
        came_from: Dict[int, int] = {}
        g_score: Dict[int, float] = {start_id: 0}
        f_score: Dict[int, float] = {start_id: h(start_id)}
        closed_set: Set[int] = set()
        
        while open_set:
            _, current = heapq.heappop(open_set)
            
            if current == goal_id:
                # Восстановление пути
                path = [current]
                while current in came_from:
                    current = came_from[current]
                    path.append(current)
                return path[::-1]
            
            if current in closed_set:
                continue
            closed_set.add(current)
            
            for neighbor, weight in self.adjacency.get(current, []):
                if neighbor in closed_set:
                    continue
                
                tentative_g = g_score[current] + weight
                
                if neighbor not in g_score or tentative_g < g_score[neighbor]:
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g
                    f_score[neighbor] = tentative_g + h(neighbor)
                    heapq.heappush(open_set, (f_score[neighbor], neighbor))
        
        return None  # Путь не найден
    
    def find_route(
        self, 
        start_room: str, 
        end_room: str
    ) -> Optional[Dict]:
        """
        Поиск маршрута между комнатами
        
        Returns:
            dict с points, total_distance, estimated_time
        """
        start_node = self.find_node_by_room(start_room)
        end_node = self.find_node_by_room(end_room)
        
        if not start_node or not end_node:
            return None
        
        path_ids = self.a_star(start_node.id, end_node.id)
        
        if not path_ids:
            return None
        
        # Формирование результата
        points = []
        total_distance = 0.0
        
        for i, node_id in enumerate(path_ids):
            node = self.nodes[node_id]
            points.append({
                "x": node.x,
                "y": node.y,
                "z": node.z
            })
            
            if i > 0:
                prev = self.nodes[path_ids[i - 1]]
                total_distance += self.euclidean_distance(prev, node)
        
        # Примерное время: 1 м/с = 60 м/мин
        estimated_time = total_distance / 60.0
        
        return {
            "points": points,
            "total_distance": total_distance,
            "estimated_time": estimated_time
        }


def a_star(
    graph: dict,
    start_id: int,
    end_id: int,
) -> Optional[List[int]]:
    """
    A* поиск пути между двумя узлами графа.

    Args:
        graph: Граф навигации как dict. node_id → {"neighbors": [(id, weight)], "pos": (x, y)}.
        start_id: ID стартового узла.
        end_id: ID конечного узла.

    Returns:
        Список node_id от start до end включительно, или None если пути нет.
    """

    # Euclidean heuristic
    def heuristic(a: int, b: int) -> float:
        ax, ay = graph[a]["pos"]
        bx, by = graph[b]["pos"]
        return math.hypot(ax - bx, ay - by)

    open_set = [(0, start_id)]
    came_from: Dict[int, int] = {}
    g_score: Dict[int, float] = {start_id: 0}

    while open_set:
        _, current = heapq.heappop(open_set)
        if current == end_id:
            path: List[int] = []
            while current in came_from:
                path.append(current)
                current = came_from[current]
            path.append(start_id)
            return list(reversed(path))
        for neighbor, weight in graph[current]["neighbors"]:
            tentative_g = g_score[current] + weight
            if tentative_g < g_score.get(neighbor, float("inf")):
                came_from[neighbor] = current
                g_score[neighbor] = tentative_g
                f = tentative_g + heuristic(neighbor, end_id)
                heapq.heappush(open_set, (f, neighbor))
    return None
