from typing import TypeAlias

NodeId: TypeAlias = int | str
EdgeId: TypeAlias = tuple[NodeId, NodeId, NodeId]
Route: TypeAlias = list[NodeId]
BikeId: TypeAlias = str
